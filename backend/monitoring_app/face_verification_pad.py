"""Helpers for mapping photo checks into face-verify behavior."""

from __future__ import annotations

from django.conf import settings

from monitoring_app.face_verification_contract import LivenessPayload
from monitoring_app.pad_diagnostics import (
    diagnostics_from_pad_result,
    filter_operator_facing_tags,
)
from monitoring_app.photo_pad import (
    STATUS_CLEAN,
    STATUS_ERROR,
    STATUS_REVIEW,
    STATUS_SUSPICIOUS,
    PadResult,
)

VERIFY_PAD_NOTE_RU = (
    "Проверка живости (PAD) выполнена на сервере в составе verify_face."
)


def pad_operator_action_from_diagnostics(diagnostics: dict[str, object]) -> str:
    decision = diagnostics.get("decision")
    if not isinstance(decision, dict):
        return ""
    return str(decision.get("operator_action") or "").strip()


def _pad_num(name: str, default: float) -> float:
    numbers = getattr(settings, "PHOTO_PAD_NUMBERS", {})
    if not isinstance(numbers, dict):
        return default
    value = numbers.get(name, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def pad_has_hard_spoof_evidence(pad: PadResult) -> bool:
    """Return true only for PAD signals strong enough to block immediately."""
    if pad.status != STATUS_SUSPICIOUS or pad.trust_confirmed is not False:
        return False

    risk = float(getattr(pad, "risk_score", 0.0) or 0.0)
    model = float(getattr(pad, "deepface_score", 0.0) or 0.0)
    device = float(getattr(pad, "device_score", 0.0) or 0.0)
    frame = float(getattr(pad, "frame_score", 0.0) or 0.0)
    recapture = float(getattr(pad, "recapture_score", 0.0) or 0.0)
    color = float(getattr(pad, "color_hist_score", 0.0) or 0.0)

    if risk >= _pad_num("public_no_risk_min", 0.72):
        return True
    if model >= _pad_num("decision_deepfake_mid_suspicious_min", 0.82):
        return True
    if device >= _pad_num("decision_suspicious_device_min", 0.34):
        return True
    if frame >= _pad_num("decision_suspicious_frame_min", 0.42):
        return True

    recapture_strong = recapture >= _pad_num("recapture_strong", 0.38)
    color_strong = color >= _pad_num("color_hist_strong", 0.40)
    has_geometry = (
        device >= _pad_num("decision_weak_device_min", 0.16)
        or frame >= _pad_num("decision_weak_frame_min", 0.20)
    )
    has_model = model >= _pad_num("decision_deepfake_review_min", 0.65)
    return (recapture_strong or color_strong) and (has_geometry or has_model)


def pad_public_decision_from_result(pad: PadResult) -> str:
    """Public three-state PAD result for UI and sockets: YES / NO / REVIEW."""
    diagnostics = diagnostics_from_pad_result(pad)
    action = pad_operator_action_from_diagnostics(diagnostics)
    if pad_has_hard_spoof_evidence(pad):
        return "NO"
    if (
        action == "reject"
        or pad.status == STATUS_SUSPICIOUS
        or pad.trust_confirmed is False
    ):
        return "REVIEW"
    if action in {"manual_review", "retry_photo"}:
        return "REVIEW"
    if action in {"accept", "accept_with_caution"} or pad.status == STATUS_CLEAN:
        return "YES"
    return "REVIEW"


def pad_allows_identity_probe(pad: PadResult) -> bool:
    """Return whether verify can trust the frame without caveats.

    Args:
        pad: Result from ``check_photo_bgr``.

    Returns:
        ``True`` only for an unambiguously clean live frame.
    """
    return pad.status == STATUS_CLEAN and pad.trust_confirmed is True


def pad_blocks_before_identity(pad: PadResult) -> bool:
    """Return whether verify must stop before identity scoring.

    Args:
        pad: Result from ``check_photo_bgr``.

    Returns:
        ``True`` for hard spoof/error outcomes. Soft insufficient-input frames are
        allowed to continue so compare can still produce a useful score.
    """
    status = str(getattr(pad, "status", "") or "").strip().lower()
    if status == STATUS_ERROR:
        return True
    if pad_public_decision_from_result(pad) == "NO":
        return True
    return status not in {
        STATUS_CLEAN,
        STATUS_REVIEW,
        STATUS_SUSPICIOUS,
        "insufficient_input_review",
    }


def pad_blocks_bootstrap_sample(pad: PadResult) -> bool:
    """Return whether bootstrap must reject the captured frame.

    Bootstrap enrollment is a controlled setup flow: PAD is stored as audit metadata,
    while face quality and embedding extraction decide whether the sample is usable.
    """
    return False


def liveness_payload_from_pad_result(pad: PadResult) -> LivenessPayload:
    """Real liveness fields for verify_face (PAD already ran).

    Returns:
        Payload including operator-facing ``tags`` (no internal ``pad_*`` blobs) and
        structured Russian ``diagnostics`` for Face Lab.
    """
    diagnostics = diagnostics_from_pad_result(pad)
    return {
        "checked": True,
        "decision": pad_public_decision_from_result(pad),
        "operator_action": pad_operator_action_from_diagnostics(diagnostics),
        "trust_confirmed": pad.trust_confirmed,
        "status": pad.status,
        "risk_score": pad.risk_score,
        "model_version": pad.model_version,
        "tags": filter_operator_facing_tags(list(pad.tags)),
        "elapsed_ms": pad.elapsed_ms,
        "deepface_score": pad.deepface_score,
        "device_score": pad.device_score,
        "frame_score": pad.frame_score,
        "quality_penalty": pad.quality_penalty,
        "device_bg_score": pad.device_bg_score,
        "frame_global_score": pad.frame_global_score,
        "recapture_score": pad.recapture_score,
        "face_reflection_score": getattr(pad, "face_reflection_score", 0.0),
        "color_hist_score": getattr(pad, "color_hist_score", 0.0),
        "note": VERIFY_PAD_NOTE_RU,
    }


def pad_blocks_identity_verification(pad: PadResult) -> bool:
    """Deprecated name; use :func:`pad_blocks_before_identity`."""
    return pad_blocks_before_identity(pad)


__all__ = [
    "VERIFY_PAD_NOTE_RU",
    "liveness_payload_from_pad_result",
    "pad_allows_identity_probe",
    "pad_blocks_before_identity",
    "pad_blocks_bootstrap_sample",
    "pad_blocks_identity_verification",
    "pad_has_hard_spoof_evidence",
    "pad_operator_action_from_diagnostics",
    "pad_public_decision_from_result",
]
