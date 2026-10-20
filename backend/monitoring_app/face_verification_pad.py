"""Helpers for mapping photo checks into face-verify behavior."""

from __future__ import annotations

from monitoring_app.face_verification_contract import LivenessPayload
from monitoring_app.pad_diagnostics import filter_operator_facing_tags
from monitoring_app.photo_pad import (
    STATUS_CLEAN,
    PadResult,
)


def pad_binary_decision(status: str) -> str:
    return "YES" if (status or "").strip().lower() == STATUS_CLEAN else "NO"


def pad_public_decision_from_result(pad: PadResult) -> str:
    """Public PAD result for UI and verify: YES or NO."""
    return pad_binary_decision(pad.status)


def liveness_payload_from_pad_result(pad: PadResult) -> LivenessPayload:
    """Real liveness fields for verify_face (PAD already ran).

    Returns:
        Payload with the binary ``decision`` and display ``tags`` (no internal ``pad_*`` blobs).
    """
    return {
        "checked": True,
        "decision": pad_public_decision_from_result(pad),
        "status": pad.status,
        "risk_score": pad.risk_score,
        "model_version": pad.model_version,
        "tags": filter_operator_facing_tags(list(pad.tags)),
        "elapsed_ms": pad.elapsed_ms,
    }


__all__ = [
    "liveness_payload_from_pad_result",
    "pad_binary_decision",
    "pad_public_decision_from_result",
]
