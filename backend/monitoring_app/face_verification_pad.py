"""
Bridge between photo_pad.PadResult and face verification JSON contract.

Identity probe (ArcFace + gallery) runs only when PAD returns a **clean** pass with
``trust_confirmed is True``. Otherwise the binary policy answers NO without scoring.
"""

from __future__ import annotations

from monitoring_app.face_verification_contract import LivenessPayload
from monitoring_app.photo_pad import STATUS_CLEAN, PadResult

VERIFY_PAD_NOTE_RU = (
    "Проверка живости (PAD) выполнена на сервере в составе verify_face."
)


def pad_allows_identity_probe(pad: PadResult) -> bool:
    """
    True only when PAD is unambiguously clean — conservative gate before 1:1 scoring.

    - ``status`` must be ``clean`` (not ``review``, ``error``, ``suspicious``, …).
    - ``trust_confirmed`` must be ``True`` (explicit live capture accepted).
    """
    return pad.status == STATUS_CLEAN and pad.trust_confirmed is True


def pad_blocks_before_identity(pad: PadResult) -> bool:
    """Inverse of :func:`pad_allows_identity_probe` (early exit without embedding)."""
    return not pad_allows_identity_probe(pad)


def liveness_payload_from_pad_result(pad: PadResult) -> LivenessPayload:
    """Real liveness fields for verify_face (PAD already ran)."""
    return {
        "checked": True,
        "trust_confirmed": pad.trust_confirmed,
        "status": pad.status,
        "risk_score": pad.risk_score,
        "model_version": pad.model_version,
        "tags": list(pad.tags),
        "elapsed_ms": pad.elapsed_ms,
        "deepface_score": pad.deepface_score,
        "device_score": pad.device_score,
        "frame_score": pad.frame_score,
        "quality_penalty": pad.quality_penalty,
        "note": VERIFY_PAD_NOTE_RU,
    }


# Backwards alias: «block» includes error/suspicious/review/…
def pad_blocks_identity_verification(pad: PadResult) -> bool:
    """Deprecated name; use :func:`pad_blocks_before_identity`."""
    return pad_blocks_before_identity(pad)


__all__ = [
    "VERIFY_PAD_NOTE_RU",
    "liveness_payload_from_pad_result",
    "pad_allows_identity_probe",
    "pad_blocks_before_identity",
    "pad_blocks_identity_verification",
]
