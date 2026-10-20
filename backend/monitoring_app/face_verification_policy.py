from __future__ import annotations

from typing import Literal

from monitoring_app.face_verification_contract import (
    R_LIVENESS_FAILED,
    R_NEAREST_IMPOSTOR_TOO_CLOSE,
    R_PAD_PIPELINE_FAILED,
    R_PROBE_QUALITY_LOW,
    R_SCORE_BELOW_VERIFIED_THRESHOLD,
    R_WEAK_ENROLLMENT,
    FaceVerifyStatus,
    LivenessPayload,
    QualityPayload,
)
from monitoring_app.face_verification_pad import pad_binary_decision

FinalDecision = Literal["YES", "NO"]


def decide_face_verify_binary(
    *,
    quality: QualityPayload,
    liveness: LivenessPayload,
    score: float,
    gallery_templates: int,
    threshold: float,
    identity_ambiguous: bool = False,
    identity_reason_codes: list[str] | None = None,
) -> tuple[
    bool,
    FinalDecision,
    str,
    FaceVerifyStatus,
    list[str],
    float,
]:
    """Return the binary compare decision used by Face Lab.

    Args:
        quality: Probe quality payload from embedding extraction.
        liveness: Photo-check payload from PAD.
        score: Best similarity score for the probe.
        gallery_templates: Count of available templates.
        threshold: Cosine threshold (one for every gallery, calibrated on AdaFace).
        identity_ambiguous: Another staff member is about as close as the claimed one.

    Returns:
        Matched flag, final decision, short summary, contract status, reason codes,
        and the applied threshold.
    """
    st_live = str(liveness.get("status") or "").strip().lower()
    liveness_decision = str(liveness.get("decision") or "").strip().upper() or (
        pad_binary_decision(st_live)
    )

    if not liveness.get("checked") or st_live == "error":
        return (
            False,
            "NO",
            "Проверка не сработала." if not liveness.get("checked") else "Кадр не обработан.",
            "PAD_ERROR",
            [R_PAD_PIPELINE_FAILED],
            0.0,
        )

    if liveness_decision != "YES":
        return (
            False,
            "NO",
            "Фото не принято.",
            "LIVENESS_FAIL",
            [R_LIVENESS_FAILED],
            0.0,
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
        )

    if int(gallery_templates) < 1:
        return (
            False,
            "NO",
            "Нет эталона для сравнения.",
            "REJECTED",
            [R_WEAK_ENROLLMENT],
            0.0,
        )

    if identity_ambiguous:
        rc = [R_NEAREST_IMPOSTOR_TOO_CLOSE]
        rc.extend(code for code in identity_reason_codes or [] if code not in rc)
        return (False, "NO", "Похоже на другого сотрудника.", "REJECTED", rc, 0.0)

    thr = float(threshold)
    if float(score) >= thr:
        return (True, "YES", "Да. Совпадение есть.", "VERIFIED", [], thr)
    return (
        False,
        "NO",
        "Сходство ниже порога.",
        "REJECTED",
        [R_SCORE_BELOW_VERIFIED_THRESHOLD],
        thr,
    )


def build_contract_core(
    *,
    matched: bool,
    final_decision: FinalDecision,
    summary: str,
    status: FaceVerifyStatus,
    threshold_applied: float,
    score: float,
    max_cosine: float,
    gallery_size: int,
    reason_codes: list[str],
    quality: QualityPayload,
    liveness: LivenessPayload,
) -> dict[str, object]:
    return {
        "matched": matched,
        "final_decision": final_decision,
        "summary": summary,
        "status": status,
        "threshold_applied": threshold_applied,
        "score": score,
        "max_cosine": max_cosine,
        "gallery_size": gallery_size,
        "reason_codes": reason_codes,
        "quality": quality,
        "liveness": liveness,
    }


__all__ = [
    "build_contract_core",
    "decide_face_verify_binary",
]
