from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from django.conf import settings
from monitoring_app.face_verification_contract import (
    R_COLD_START_QUALITY_INSUFFICIENT,
    R_LIVENESS_FAILED,
    R_LIVENESS_UNCERTAIN,
    R_NEAREST_IMPOSTOR_TOO_CLOSE,
    R_PAD_PIPELINE_FAILED,
    R_PROBE_QUALITY_LOW,
    R_SCORE_BELOW_COLD_START_THRESHOLD,
    R_SCORE_BELOW_VERIFIED_THRESHOLD,
    R_SCORE_BELOW_WEAK_GALLERY_THRESHOLD,
    R_WEAK_ENROLLMENT,
    FaceVerifyStatus,
    GalleryInfoPayload,
    LivenessPayload,
    QualityPayload,
)

FinalDecision = Literal["YES", "NO"]


def _distinct_enrollment_sources(breakdown: Mapping[str, int]) -> int:
    n = 0
    if breakdown.get("mask_prototypes", 0) > 0:
        n += 1
    if breakdown.get("avatar_prototypes", 0) > 0:
        n += 1
    if breakdown.get("face_sample_prototypes", 0) > 0:
        n += 1
    if breakdown.get("gallery_real_npy_prototypes", 0) > 0:
        n += 1
    return n


def build_gallery_info(
    *,
    gallery_templates: int,
    breakdown: Mapping[str, int],
) -> GalleryInfoPayload:
    distinct = _distinct_enrollment_sources(breakdown)
    return {
        "total_templates": gallery_templates,
        "distinct_enrollment_sources": distinct,
    }


def _cold_start_guard_quality(quality: QualityPayload) -> bool:
    """Stricter probe quality than normal verify; only used on cold-start path."""
    min_det = float(getattr(settings, "FACE_VERIFY_COLD_START_DET_MIN", 0.42))
    min_area = float(getattr(settings, "FACE_VERIFY_COLD_START_FACE_AREA_MIN", 0.012))
    det = quality.get("det_score")
    area = quality.get("face_area_ratio")
    if not isinstance(det, (int, float)) or float(det) < min_det:
        return False
    if not isinstance(area, (int, float)) or float(area) < min_area:
        return False
    return True


def _cold_start_response_strength(
    *,
    quality: QualityPayload,
    score: float,
    threshold_weak_gallery: float,
    threshold_cold_start: float,
) -> Literal["strong", "weak"]:
    score_margin = float(
        getattr(settings, "FACE_VERIFY_COLD_START_STRONG_SCORE_MARGIN", 0.025)
    )
    min_score = max(
        float(threshold_weak_gallery),
        float(threshold_cold_start) + score_margin,
    )
    min_det = float(getattr(settings, "FACE_VERIFY_COLD_START_STRONG_DET_MIN", 0.72))
    min_area = float(
        getattr(settings, "FACE_VERIFY_COLD_START_STRONG_FACE_AREA_MIN", 0.04)
    )
    det = quality.get("det_score")
    area = quality.get("face_area_ratio")
    if (
        isinstance(det, (int, float))
        and isinstance(area, (int, float))
        and float(score) >= min_score
        and float(det) >= min_det
        and float(area) >= min_area
    ):
        return "strong"
    return "weak"


def _single_photo_relaxed_allowed(
    *,
    quality: QualityPayload,
    score: float,
    identity_gap: float | None,
    gallery_templates: int,
    breakdown: Mapping[str, int],
) -> bool:
    if not bool(getattr(settings, "FACE_VERIFY_SINGLE_PHOTO_RELAXED_ENABLE", True)):
        return False
    min_templates = int(getattr(settings, "FACE_VERIFY_SINGLE_PHOTO_MIN_TEMPLATES", 3))
    if int(gallery_templates) < min_templates:
        return False
    if int(breakdown.get("avatar_prototypes") or 0) < 1:
        return False
    runtime_variants = int(breakdown.get("condition_variant_prototypes") or 0) + int(
        breakdown.get("glasses_variant_prototypes") or 0
    )
    if runtime_variants < 2:
        return False
    if not _cold_start_guard_quality(quality):
        return False
    if identity_gap is None:
        return False
    gap_min = float(getattr(settings, "FACE_VERIFY_SINGLE_PHOTO_GAP_MIN", 0.16))
    if float(identity_gap) < gap_min:
        return False
    thr = float(getattr(settings, "FACE_VERIFY_SINGLE_PHOTO_THRESHOLD", 0.76))
    return float(score) >= thr


def is_strong_gallery(breakdown: Mapping[str, int], gallery_templates: int) -> bool:
    """
    Strong gallery: at least FACE_VERIFY_MIN_ENROLLMENT_SOURCES distinct prototype
    origins and at least FACE_VERIFY_MIN_TEMPLATES_STRONG rows — matches product rule.

    A single avatar with enough test-time-augmentation variants (different
    lighting/glasses conditions rendered from the same source photo) also
    counts as strong: most staff only ever upload one avatar, and refusing to
    trust 5+ independently-rendered variants of it just because they share one
    origin file punishes the common case instead of a real enrollment risk.
    """
    distinct = _distinct_enrollment_sources(breakdown)
    need_src = int(getattr(settings, "FACE_VERIFY_MIN_ENROLLMENT_SOURCES", 2))
    need_tpl = int(getattr(settings, "FACE_VERIFY_MIN_TEMPLATES_STRONG", 2))
    if distinct >= need_src and gallery_templates >= need_tpl:
        return True

    single_source_min_templates = int(
        getattr(settings, "FACE_VERIFY_SINGLE_SOURCE_STRONG_MIN_TEMPLATES", 5)
    )
    return (
        distinct == 1
        and int(breakdown.get("avatar_prototypes") or 0) > 0
        and gallery_templates >= single_source_min_templates
    )


def decide_face_verify_binary(
    *,
    quality: QualityPayload,
    liveness: LivenessPayload,
    score: float,
    gallery_templates: int,
    breakdown: Mapping[str, int],
    threshold_verified: float,
    threshold_weak_gallery: float,
    threshold_cold_start: float,
    identity_ambiguous: bool = False,
    identity_reason_codes: list[str] | None = None,
    identity_gap: float | None = None,
) -> tuple[
    bool,
    FinalDecision,
    str,
    FaceVerifyStatus,
    list[str],
    float,
    Literal["strong", "weak"],
]:
    """Return the binary compare decision used by Face Lab.

    Args:
        quality: Probe quality payload from embedding extraction.
        liveness: Photo-check payload from PAD.
        score: Best similarity score for the probe.
        gallery_templates: Count of available templates.
        breakdown: Template-source breakdown.
        threshold_verified: Normal strong-gallery threshold.
        threshold_weak_gallery: Weak-gallery threshold.
        threshold_cold_start: Cold-start threshold.

    Returns:
        Matched flag, final decision, short summary, contract status, reason codes,
        applied threshold, and gallery strength.
    """
    st_live = str(liveness.get("status") or "").strip().lower()
    public_liveness_decision = str(liveness.get("decision") or "").strip().upper()
    tc = liveness.get("trust_confirmed")
    diag = liveness.get("diagnostics")
    decision = diag.get("decision") if isinstance(diag, Mapping) else None
    operator_action = (
        str(liveness.get("operator_action") or decision.get("operator_action") or "")
        .strip()
        .lower()
        if isinstance(decision, Mapping)
        else str(liveness.get("operator_action") or "").strip().lower()
    )
    liveness_accepted_with_caution = (
        public_liveness_decision == "YES"
        or (
            st_live == "clean"
            and tc is None
            and operator_action == "accept_with_caution"
        )
    )
    liveness_rejected = public_liveness_decision == "NO"
    liveness_uncertain = (
        public_liveness_decision == "REVIEW"
        or st_live in {"review", "insufficient_input_review"}
        or operator_action in {"manual_review", "retry_photo"}
    )
    current_gallery_strength: Literal["strong", "weak"] = (
        "strong" if is_strong_gallery(breakdown, gallery_templates) else "weak"
    )

    if not liveness.get("checked"):
        return (
            False,
            "NO",
            "Проверка не сработала.",
            "PAD_ERROR",
            [R_PAD_PIPELINE_FAILED],
            0.0,
            "weak",
        )

    if st_live == "error":
        return (
            False,
            "NO",
            "Кадр не обработан.",
            "PAD_ERROR",
            [R_PAD_PIPELINE_FAILED],
            0.0,
            "weak",
        )

    if liveness_rejected:
        return (
            False,
            "NO",
            "Фото не принято.",
            "LIVENESS_FAIL",
            [R_LIVENESS_FAILED],
            0.0,
            current_gallery_strength,
        )

    if (tc is False or st_live == "suspicious") and not liveness_uncertain:
        return (
            False,
            "NO",
            "Фото не принято.",
            "LIVENESS_FAIL",
            [R_LIVENESS_FAILED],
            0.0,
            current_gallery_strength,
        )

    if (
        (tc is not True or st_live != "clean")
        and not liveness_accepted_with_caution
        and not liveness_uncertain
    ):
        return (
            False,
            "NO",
            "Система сомневается.",
            "LIVENESS_FAIL",
            [R_LIVENESS_UNCERTAIN],
            0.0,
            current_gallery_strength,
        )

    if not quality.get("passed", False):
        rc = list(quality.get("reason_codes") or [])
        reason_codes = [R_PROBE_QUALITY_LOW]
        reason_codes.extend(x for x in rc if x not in reason_codes)
        return (
            False,
            "NO",
            "Нужен новый кадр.",
            "QUALITY_FAIL",
            reason_codes,
            0.0,
            "weak",
        )

    if int(gallery_templates) < 1:
        return (
            False,
            "NO",
            "Нет эталона для сравнения.",
            "REJECTED",
            [R_WEAK_ENROLLMENT],
            0.0,
            "weak",
        )

    strong = is_strong_gallery(breakdown, gallery_templates)
    gallery_strength: Literal["strong", "weak"] = "strong" if strong else "weak"

    if identity_ambiguous:
        rc = [R_NEAREST_IMPOSTOR_TOO_CLOSE]
        for code in identity_reason_codes or []:
            if code not in rc:
                rc.append(code)
        return (
            False,
            "NO",
            "Похоже на другого сотрудника.",
            "REJECTED",
            rc,
            0.0,
            "weak",
        )

    if strong:
        thr = float(threshold_verified)
        if float(score) >= thr:
            summary = (
                "Да. Фото принято."
                if liveness_uncertain
                else "Да. Совпадение есть."
            )
            return (
                True,
                "YES",
                summary,
                "VERIFIED",
                [],
                thr,
                gallery_strength,
            )
        relaxed_enabled = bool(
            getattr(settings, "FACE_VERIFY_STRONG_GALLERY_RELAXED_ENABLE", True)
        )
        relaxed_thr = float(
            getattr(settings, "FACE_VERIFY_STRONG_GALLERY_RELAXED_THRESHOLD", 0.74)
        )
        relaxed_gap_min = float(
            getattr(settings, "FACE_VERIFY_STRONG_GALLERY_RELAXED_GAP_MIN", 0.12)
        )
        if (
            relaxed_enabled
            and identity_gap is not None
            and float(score) >= relaxed_thr
            and float(identity_gap) >= relaxed_gap_min
        ):
            summary = (
                "Да. Фото принято."
                if liveness_uncertain
                else "Да. Совпадение есть."
            )
            return (
                True,
                "YES",
                summary,
                "VERIFIED",
                [],
                relaxed_thr,
                gallery_strength,
            )
        return (
            False,
            "NO",
            "Сходство ниже порога.",
            "REJECTED",
            [R_SCORE_BELOW_VERIFIED_THRESHOLD],
            thr,
            gallery_strength,
        )

    n_real = int(breakdown.get("gallery_real_npy_prototypes") or 0)
    cold_start_path = n_real == 0

    if cold_start_path:
        if not _cold_start_guard_quality(quality):
            return (
                False,
                "NO",
                "Нужен кадр крупнее.",
                "REJECTED",
                [R_COLD_START_QUALITY_INSUFFICIENT],
                0.0,
                "weak",
            )
        if _single_photo_relaxed_allowed(
            quality=quality,
            score=float(score),
            identity_gap=identity_gap,
            gallery_templates=int(gallery_templates),
            breakdown=breakdown,
        ):
            thr_sp = float(getattr(settings, "FACE_VERIFY_SINGLE_PHOTO_THRESHOLD", 0.76))
            summary = (
                "Да. Фото принято."
                if liveness_uncertain
                else "Да. Совпадение есть."
            )
            return (
                True,
                "YES",
                summary,
                "VERIFIED",
                [],
                thr_sp,
                "weak",
            )
        thr_c = float(threshold_cold_start)
        if float(score) >= thr_c:
            summary = (
                "Да. Фото принято."
                if liveness_uncertain
                else "Да. Совпадение есть."
            )
            response_strength = _cold_start_response_strength(
                quality=quality,
                score=float(score),
                threshold_weak_gallery=float(threshold_weak_gallery),
                threshold_cold_start=thr_c,
            )
            return (
                True,
                "YES",
                summary,
                "VERIFIED",
                [],
                thr_c,
                response_strength,
            )
        return (
            False,
            "NO",
            "Сходство ниже порога.",
            "REJECTED",
            [R_SCORE_BELOW_COLD_START_THRESHOLD],
            thr_c,
            "weak",
        )

    thr_w = float(threshold_weak_gallery)
    if float(score) >= thr_w:
        summary = (
            "Да. Фото принято."
            if liveness_uncertain
            else "Да. Совпадение есть."
        )
        return (
            True,
            "YES",
            summary,
            "VERIFIED",
            [],
            thr_w,
            gallery_strength,
        )
    rc = [R_WEAK_ENROLLMENT, R_SCORE_BELOW_WEAK_GALLERY_THRESHOLD]
    return (
        False,
        "NO",
        "Сходство ниже порога.",
        "REJECTED",
        list(dict.fromkeys(rc)),
        thr_w,
        gallery_strength,
    )


def build_contract_core(
    *,
    matched: bool,
    final_decision: FinalDecision,
    summary: str,
    status: FaceVerifyStatus,
    gallery_strength: Literal["strong", "weak"],
    threshold_applied: float,
    score: float,
    max_cosine: float,
    threshold_verified_strong: float,
    threshold_verified_weak: float,
    gallery_size: int,
    reason_codes: list[str],
    quality: QualityPayload,
    liveness: LivenessPayload,
    gallery: GalleryInfoPayload,
) -> dict[str, object]:
    return {
        "matched": matched,
        "final_decision": final_decision,
        "summary": summary,
        "decision_summary": summary,
        "status": status,
        "gallery_strength": gallery_strength,
        "threshold_applied": threshold_applied,
        "score": score,
        "max_cosine": max_cosine,
        "threshold_verified_strong": threshold_verified_strong,
        "threshold_verified_weak": threshold_verified_weak,
        "gallery_size": gallery_size,
        "reason_codes": reason_codes,
        "quality": quality,
        "liveness": liveness,
        "gallery": gallery,
    }


__all__ = [
    "build_contract_core",
    "build_gallery_info",
    "decide_face_verify_binary",
    "is_strong_gallery",
]
