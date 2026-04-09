"""Helpers for mapping photo checks into face-verify behavior."""

from __future__ import annotations

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
    if getattr(pad, "trust_confirmed", None) is False:
        return True
    if status in {STATUS_ERROR, STATUS_SUSPICIOUS}:
        return True
    return status not in {STATUS_CLEAN, STATUS_REVIEW, "insufficient_input_review"}


def pad_blocks_bootstrap_sample(pad: PadResult) -> bool:
    """Return whether bootstrap must reject the captured frame.

    Args:
        pad: Result from ``check_photo_bgr``.

    Returns:
        ``True`` only for clear spoof-like frames. Soft review or insufficient-input
        outcomes stay non-blocking in the three-photo setup flow.
    """
    status = str(getattr(pad, "status", "") or "").strip().lower()
    return getattr(pad, "trust_confirmed", None) is False or status == STATUS_SUSPICIOUS


def liveness_payload_from_pad_result(pad: PadResult) -> LivenessPayload:
    """Real liveness fields for verify_face (PAD already ran).

    Returns:
        Payload including operator-facing ``tags`` (no internal ``pad_*`` blobs) and
        structured Russian ``diagnostics`` for Face Lab.
    """
    return {
        "checked": True,
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
        "diagnostics": diagnostics_from_pad_result(pad),
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
]
