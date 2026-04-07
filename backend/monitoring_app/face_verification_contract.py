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
R_SCORE_BELOW_WEAK_GALLERY_THRESHOLD = "SCORE_BELOW_WEAK_GALLERY_THRESHOLD"
R_WEAK_ENROLLMENT = "WEAK_ENROLLMENT"
R_LIVENESS_FAILED = "LIVENESS_FAILED"
R_PAD_PIPELINE_FAILED = "PAD_PIPELINE_FAILED"
R_SCORE_BELOW_COLD_START_THRESHOLD = "SCORE_BELOW_COLD_START_THRESHOLD"
R_COLD_START_QUALITY_INSUFFICIENT = "COLD_START_QUALITY_INSUFFICIENT"


class GalleryBreakdownPayload(TypedDict, total=False):
    mask_prototypes: int
    avatar_prototypes: int
    gallery_real_npy_prototypes: int


class QualityPayload(TypedDict, total=False):
    passed: bool
    det_score: float | None
    face_area_ratio: float | None
    reason_codes: list[str]


class LivenessPayload(TypedDict, total=False):
    checked: bool
    trust_confirmed: bool | None
    status: str | None
    risk_score: float | None
    model_version: str | None
    tags: list[str]
    elapsed_ms: float
    deepface_score: float
    device_score: float
    frame_score: float
    quality_penalty: float
    note: str


class GalleryInfoPayload(TypedDict, total=False):
    total_templates: int
    distinct_enrollment_sources: int


GalleryStrength = Literal["strong", "weak"]
FinalDecision = Literal["YES", "NO"]


class FaceVerifyContractPayload(TypedDict, total=False):
    matched: bool
    final_decision: str
    summary: str
    decision_summary: str
    status: str
    gallery_strength: str
    threshold_applied: float
    score: float
    max_cosine: float
    threshold_verified_strong: float
    threshold_verified_weak: float
    gallery_size: int
    reason_codes: list[str]
    quality: QualityPayload
    liveness: LivenessPayload
    gallery: GalleryInfoPayload
    debug: dict[str, object]


__all__ = (
    "VERIFY_MODE_1_1",
    "FaceVerifyStatus",
    "FinalDecision",
    "GalleryBreakdownPayload",
    "GalleryInfoPayload",
    "GalleryStrength",
    "FaceVerifyContractPayload",
    "LivenessPayload",
    "QualityPayload",
    "R_LIVENESS_FAILED",
    "R_PAD_PIPELINE_FAILED",
    "R_SCORE_BELOW_COLD_START_THRESHOLD",
    "R_COLD_START_QUALITY_INSUFFICIENT",
    "R_PROBE_QUALITY_LOW",
    "R_SCORE_BELOW_VERIFIED_THRESHOLD",
    "R_SCORE_BELOW_WEAK_GALLERY_THRESHOLD",
    "R_WEAK_ENROLLMENT",
)
