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


def is_strong_gallery(breakdown: Mapping[str, int], gallery_templates: int) -> bool:
    """
    Strong gallery: at least FACE_VERIFY_MIN_ENROLLMENT_SOURCES distinct prototype
    origins and at least FACE_VERIFY_MIN_TEMPLATES_STRONG rows — matches product rule.
    """
    distinct = _distinct_enrollment_sources(breakdown)
    need_src = int(getattr(settings, "FACE_VERIFY_MIN_ENROLLMENT_SOURCES", 2))
    need_tpl = int(getattr(settings, "FACE_VERIFY_MIN_TEMPLATES_STRONG", 2))
    return distinct >= need_src and gallery_templates >= need_tpl


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
    tc = liveness.get("trust_confirmed")
    liveness_uncertain_retry = st_live in {"review", "insufficient_input_review"}
    current_gallery_strength: Literal["strong", "weak"] = (
        "strong" if is_strong_gallery(breakdown, gallery_templates) else "weak"
    )

    if not liveness.get("checked"):
        return (
            False,
            "NO",
            "Проверка не выполнена.",
            "PAD_ERROR",
            [R_PAD_PIPELINE_FAILED],
            0.0,
            "weak",
        )

    if st_live == "error":
        return (
            False,
            "NO",
            "Кадр не обработан (PAD).",
            "PAD_ERROR",
            [R_PAD_PIPELINE_FAILED],
            0.0,
            "weak",
        )

    if tc is False:
        return (
            False,
            "NO",
            "Живость не подтверждена.",
            "LIVENESS_FAIL",
            [R_LIVENESS_FAILED],
            0.0,
            current_gallery_strength,
        )

    if st_live == "suspicious":
        return (
            False,
            "NO",
            "Живость не подтверждена безусловно.",
            "LIVENESS_FAIL",
            [R_LIVENESS_FAILED],
            0.0,
            current_gallery_strength,
        )

    if liveness_uncertain_retry:
        return (
            False,
            "NO",
            "Автоматическая проверка фото не дала уверенного живого кадра: "
            "совпадение не подтверждено.",
            "QUALITY_FAIL",
            [R_LIVENESS_UNCERTAIN],
            0.0,
            current_gallery_strength,
        )

    if tc is not True or st_live != "clean":
        return (
            False,
            "NO",
            "Живость не подтверждена безусловно.",
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
            "Качество кадра или детекция недостаточны.",
            "QUALITY_FAIL",
            reason_codes,
            0.0,
            "weak",
        )

    if int(gallery_templates) < 1:
        return (
            False,
            "NO",
            "Нет эталона для сравнения на сервере.",
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
            "Лицо слишком близко к другому сотруднику: совпадение не подтверждено.",
            "REJECTED",
            rc,
            0.0,
            gallery_strength,
        )

    if strong:
        thr = float(threshold_verified)
        if float(score) >= thr:
            return (
                True,
                "YES",
                "Совпадение подтверждено.",
                "VERIFIED",
                [],
                thr,
                gallery_strength,
            )
        return (
            False,
            "NO",
            "Недостаточно надёжное совпадение.",
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
                "Для первичной проверки без собранной галереи нужен более уверенный "
                "кадр (крупнее лицо и выше уверенность детектора).",
                "REJECTED",
                [R_COLD_START_QUALITY_INSUFFICIENT],
                0.0,
                "weak",
            )
        thr_c = float(threshold_cold_start)
        if float(score) >= thr_c:
            summary = (
                "Совпадение подтверждено (режим холодного старта до сборки галереи)."
            )
            return (
                True,
                "YES",
                summary,
                "VERIFIED",
                [],
                thr_c,
                "weak",
            )
        return (
            False,
            "NO",
            "Недостаточно сходство для режима холодного старта (галерея ещё не собрана).",
            "REJECTED",
            [R_SCORE_BELOW_COLD_START_THRESHOLD],
            thr_c,
            "weak",
        )

    thr_w = float(threshold_weak_gallery)
    if float(score) >= thr_w:
        return (
            True,
            "YES",
            "Совпадение подтверждено (строгий порог для слабой галереи).",
            "VERIFIED",
            [],
            thr_w,
            gallery_strength,
        )
    rc = [R_WEAK_ENROLLMENT, R_SCORE_BELOW_WEAK_GALLERY_THRESHOLD]
    return (
        False,
        "NO",
        "Слабая галерея эталонов — применён строгий порог; совпадение не подтверждено.",
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
