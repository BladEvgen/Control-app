from __future__ import annotations

from typing import Literal, TypedDict

FaceVerifyStatus = Literal[
    "VERIFIED",
    "REJECTED",
    "QUALITY_FAIL",
    "LIVENESS_FAIL",
    "PAD_ERROR",
]

VERIFY_MODE_1_1 = "VERIFY_1_1"

R_PROBE_QUALITY_LOW = "PROBE_QUALITY_LOW"
R_SCORE_BELOW_VERIFIED_THRESHOLD = "SCORE_BELOW_VERIFIED_THRESHOLD"
R_WEAK_ENROLLMENT = "WEAK_ENROLLMENT"
R_LIVENESS_FAILED = "LIVENESS_FAILED"
R_PAD_PIPELINE_FAILED = "PAD_PIPELINE_FAILED"
R_NEAREST_IMPOSTOR_TOO_CLOSE = "NEAREST_IMPOSTOR_TOO_CLOSE"


class GalleryBreakdownPayload(TypedDict, total=False):
    mask_prototypes: int
    avatar_prototypes: int
    face_sample_prototypes: int
    centroid_prototypes: int
    gallery_real_npy_prototypes: int


class QualityPayload(TypedDict, total=False):
    passed: bool
    det_score: float | None
    face_area_ratio: float | None
    blur_laplacian_var: float | None
    brightness_mean: float | None
    pose_yaw: float | None
    pose_pitch: float | None
    pose_roll: float | None
    reason_codes: list[str]


def _optional_float(v: object) -> float | None:
    if isinstance(v, bool):
        return None
    return float(v) if isinstance(v, (int, float)) else None


_QUALITY_FLOAT_KEYS = (
    "det_score",
    "face_area_ratio",
    "blur_laplacian_var",
    "brightness_mean",
    "pose_yaw",
    "pose_pitch",
    "pose_roll",
)


def quality_payload_from_probe_meta(probe_meta: dict[str, object]) -> QualityPayload:
    """Блок ``quality`` ответа verify из метаданных пробы ``ml.create_face_encoding_with_probe_meta``."""
    raw_codes = probe_meta.get("quality_reason_codes")
    payload: QualityPayload = {
        "passed": bool(probe_meta.get("quality_pass")),
        "reason_codes": [str(x) for x in raw_codes] if isinstance(raw_codes, list) else [],
    }
    for key in _QUALITY_FLOAT_KEYS:
        payload[key] = _optional_float(probe_meta.get(key))  # type: ignore[literal-required]
    return payload


class LivenessPayload(TypedDict, total=False):
    checked: bool
    decision: str
    status: str | None
    risk_score: float | None
    model_version: str | None
    tags: list[str]
    elapsed_ms: float


FinalDecision = Literal["YES", "NO"]


class FaceVerifyContractPayload(TypedDict, total=False):
    matched: bool
    final_decision: str
    summary: str
    status: str
    threshold_applied: float
    score: float
    max_cosine: float
    gallery_size: int
    reason_codes: list[str]
    quality: QualityPayload
    liveness: LivenessPayload
    debug: dict[str, object]


__all__ = (
    "VERIFY_MODE_1_1",
    "FaceVerifyStatus",
    "FinalDecision",
    "GalleryBreakdownPayload",
    "FaceVerifyContractPayload",
    "LivenessPayload",
    "QualityPayload",
    "R_LIVENESS_FAILED",
    "R_PAD_PIPELINE_FAILED",
    "R_NEAREST_IMPOSTOR_TOO_CLOSE",
    "R_PROBE_QUALITY_LOW",
    "R_SCORE_BELOW_VERIFIED_THRESHOLD",
    "R_WEAK_ENROLLMENT",
    "quality_payload_from_probe_meta",
)
