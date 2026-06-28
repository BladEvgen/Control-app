from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, cast

import cv2
import numpy as np
from django.conf import settings
from monitoring_app import ml
from monitoring_app.pad_diagnostics import PAD_TRACE_SCHEMA
from monitoring_app.pad_evidence import (
    device_presentation_relevant,
    face_bbox_to_xyxy,
    frame_quad_face_relevant,
    intersection_area_xyxy,
    signal_recapture_face_roi,
)

logger = logging.getLogger(__name__)

PAD_MODEL_VERSION = "pad_v12"

STATUS_PENDING = "pending"
STATUS_CLEAN = "clean"
STATUS_REVIEW = "review"
STATUS_SUSPICIOUS = "suspicious"
STATUS_ERROR = "error"

MANUAL_NONE = "none"

DEVICE_AUTO = "auto"
DEVICE_CPU = "cpu"
DEVICE_CUDA = "cuda"
DEVICE_VALUES = {DEVICE_AUTO, DEVICE_CPU, DEVICE_CUDA}

_COCO_DEVICE_CLASSES = {
    77: "cell phone",
    73: "laptop",
    72: "tv",
}

_runtime_cache: dict[str, Any] = {}
_runtime_cache_lock = threading.RLock()
_guide_face_detector_infer_lock = threading.Lock()


def _clamp01(value: float) -> float:
    """Clamp a numeric signal to the PAD score range."""
    try:
        v = float(value)
    except Exception:
        return 0.0
    if not np.isfinite(v):
        return 0.0
    return float(max(0.0, min(1.0, v)))


def _cv2_get_attr(name: str) -> Any:
    attr = getattr(cv2, name, None)
    if attr is None:
        raise RuntimeError(f"cv2 attribute is unavailable: {name}")
    return attr


def _cv2_get_callable(name: str) -> Callable[..., Any]:
    attr = _cv2_get_attr(name)
    if not callable(attr):
        raise RuntimeError(f"cv2 callable is unavailable: {name}")
    return cast(Callable[..., Any], attr)


_CV2_IMREAD = _cv2_get_callable("imread")
_CV2_CVT_COLOR = _cv2_get_callable("cvtColor")
_CV2_CANNY = _cv2_get_callable("Canny")
_CV2_GAUSSIAN_BLUR = _cv2_get_callable("GaussianBlur")
_CV2_GET_STRUCTURING_ELEMENT = _cv2_get_callable("getStructuringElement")
_CV2_DILATE = _cv2_get_callable("dilate")
_CV2_FIND_CONTOURS = _cv2_get_callable("findContours")
_CV2_CONTOUR_AREA = _cv2_get_callable("contourArea")
_CV2_ARC_LENGTH = _cv2_get_callable("arcLength")
_CV2_APPROX_POLY_DP = _cv2_get_callable("approxPolyDP")
_CV2_BOUNDING_RECT = _cv2_get_callable("boundingRect")
_CV2_LAPLACIAN = _cv2_get_callable("Laplacian")
_CV2_RESIZE = _cv2_get_callable("resize")
_CV2_CONNECTED_COMPONENTS_WITH_STATS = _cv2_get_callable(
    "connectedComponentsWithStats"
)

_CV2_COLOR_BGR2RGB = int(_cv2_get_attr("COLOR_BGR2RGB"))
_CV2_COLOR_BGR2GRAY = int(_cv2_get_attr("COLOR_BGR2GRAY"))
_CV2_COLOR_BGR2HSV = int(_cv2_get_attr("COLOR_BGR2HSV"))
_CV2_COLOR_BGR2YCrCb = int(_cv2_get_attr("COLOR_BGR2YCrCb"))
_CV2_COLOR_BGR2Luv = int(_cv2_get_attr("COLOR_BGR2Luv"))
_CV2_MORPH_RECT = int(_cv2_get_attr("MORPH_RECT"))
_CV2_MORPH_ELLIPSE = int(_cv2_get_attr("MORPH_ELLIPSE"))
_CV2_RETR_EXTERNAL = int(_cv2_get_attr("RETR_EXTERNAL"))
_CV2_CHAIN_APPROX_SIMPLE = int(_cv2_get_attr("CHAIN_APPROX_SIMPLE"))
_CV2_CV_64F = int(_cv2_get_attr("CV_64F"))
_CV2_INTER_AREA = int(_cv2_get_attr("INTER_AREA"))

_CV2_CREATE_CLAHE: Optional[Callable[..., Any]] = None
try:
    _CV2_CREATE_CLAHE = _cv2_get_callable("createCLAHE")
except RuntimeError:
    pass

_PAD_DEFAULT_NUMBERS: dict[str, float | int] = {
    "device_min_conf": 0.16,
    "device_min_area_ratio": 0.015,
    "device_ratio_ref": 0.25,
    "device_score_conf_weight": 0.60,
    "device_score_ratio_weight": 0.40,
    "frame_canny_low": 50,
    "frame_canny_high": 160,
    "frame_gaussian_kernel": 5,
    "frame_dilate_kernel": 3,
    "frame_min_area_ratio": 0.10,
    "frame_poly_epsilon": 0.02,
    "frame_min_solidity": 0.80,
    "frame_ratio_ref": 0.55,
    "frame_face_bonus": 0.15,
    "frame_border_bonus": 0.08,
    "frame_border_margin_px": 8,
    "frame_tag_threshold": 0.30,
    "quality_blur_min": 45.0,
    "quality_brightness_min": 35.0,
    "quality_brightness_max": 225.0,
    "quality_contrast_min": 24.0,
    "quality_face_ratio_min": 0.035,
    "quality_penalty_blur": 0.35,
    "quality_penalty_exposure": 0.20,
    "quality_penalty_contrast": 0.20,
    "quality_penalty_small_face": 0.25,
    "quality_poor_threshold": 0.45,
    "risk_weight_deepface": 0.46,
    "risk_weight_device": 0.22,
    "risk_weight_frame": 0.12,
    "decision_device_present_min": 0.24,
    "decision_device_confirmed_strong_min": 0.48,
    "decision_device_confirmed_single_min": 0.36,
    "decision_frame_present_min": 0.34,
    "decision_strong_device_min": 0.40,
    "decision_strong_frame_min": 0.34,
    "decision_quality_poor_min": 0.45,
    "decision_deepfake_review_min": 0.65,
    "decision_deepfake_device_min": 0.92,
    "decision_deepfake_very_high": 0.985,
    "decision_deepfake_mid_suspicious_min": 0.82,
    "decision_mid_device_min": 0.20,
    "decision_mid_frame_min": 0.24,
    "decision_quality_combined_review_sum_min": 0.54,
    "decision_quality_device_review_min": 0.20,
    "decision_quality_frame_review_min": 0.24,
    "decision_suspicious_device_min": 0.34,
    "decision_suspicious_frame_min": 0.42,
    "decision_weak_device_min": 0.16,
    "decision_weak_frame_min": 0.20,
    "decision_weak_combined_sum_min": 0.24,
    "pad_max_long_side": 960,
    "glasses_mask_min_pixels": 24,
    "glasses_mask_dilate": 11,
    "glasses_device_overlap_skip": 0.42,
    "glasses_device_overlap_soft": 0.14,
    "device_face_expand_scale": 1.38,
    "device_face_iou_min": 0.04,
    "device_face_cover_ratio_min": 0.14,
    "frame_face_expand_scale": 1.42,
    "frame_face_iou_min": 0.08,
    "frame_face_max_quad_area_ratio": 0.48,
    "frame_face_min_cover_when_large_quad": 0.40,
    "recapture_fft_ring_inner": 8,
    "recapture_fft_ring_outer": 42,
    "recapture_fft_baseline": 0.42,
    "recapture_fft_scale": 0.24,
    "recapture_sobel_aniso_min": 2.05,
    "recapture_sobel_aniso_scale": 0.35,
    "recapture_mid": 0.22,
    "recapture_strong": 0.38,
    "recapture_isolated_extreme_single_channel_min": 0.90,
    "recapture_isolated_moire_forgive_min_rec": 0.84,
    "recapture_isolated_moire_max_quality_penalty": 0.10,
    "risk_weight_recapture": 0.20,
    "decision_recapture_review_min": 0.18,
    "decision_recapture_corroboration_min": 0.26,
    "recapture_inner_face_scale": 0.62,
    "recapture_min_laplacian_var": 18.0,
    "recapture_blur_dampen_factor": 0.38,
    "shield_max_device_face": 0.168,
    "shield_max_frame_face": 0.198,
    "shield_max_recapture": 0.18,
    "shield_max_quality_penalty": 0.38,
    "no_fake_susp_min_face_area_ratio": 0.034,
    "quality_degraded_force_review_penalty_min": 0.55,
    "presentation_texture_min_face_area_ratio": 0.042,
    "presentation_texture_max_quality_penalty": 0.30,
    "reflection_white_v_min": 218.0,
    "reflection_white_s_max": 95.0,
    "reflection_color_v_min": 188.0,
    "reflection_color_s_min": 90.0,
    "reflection_component_min_area_ratio": 0.00035,
    "reflection_component_max_area_ratio": 0.10,
    "reflection_review_min": 0.24,
    "reflection_mid": 0.34,
    "reflection_strong": 0.52,
    "reflection_suspicious_min_face_area_ratio": 0.034,
    "risk_weight_reflection": 0.10,
    "color_hist_inner_face_scale": 0.76,
    "color_hist_mid": 0.24,
    "color_hist_strong": 0.40,
    "color_hist_low_entropy_ref": 0.58,
    "color_hist_peak_mass_ref": 0.32,
    "color_hist_sparse_occupancy_ref": 0.56,
    "color_hist_flat_chroma_std": 13.0,
    "color_hist_luma_std_min": 22.0,
    "color_hist_min_face_area_ratio": 0.034,
    "guide_face_detector_conf_min": 0.50,
    "guide_color_model_mid": 0.50,
    "guide_color_model_strong": 0.70,
    "minifasnet_onnx_crop_scale": 2.70,
    "minifasnet_onnx_mid": 0.50,
    "minifasnet_onnx_strong": 0.70,
    "spoof_model_family_mid": 0.45,
    "spoof_model_family_strong": 0.70,
    "spoof_model_disagreement_min": 0.45,
    "ensemble_review_vote_min": 0.35,
    "ensemble_strong_vote_min": 0.58,
    "ensemble_suspicious_score_min": 0.52,
    "ensemble_review_score_min": 0.30,
    "ensemble_suspicious_family_min": 2,
    "risk_weight_color_hist": 0.10,
    "shield_max_color_hist": 0.20,
    "color_hist_heuristic_only_scale": 0.80,
    "color_hist_strong_feature_min": 0.48,
    "color_hist_full_score_features_min": 3,
}


def _pad_config_value(name: str) -> float | int:
    configured = getattr(settings, "PHOTO_PAD_NUMBERS", None)
    if isinstance(configured, dict) and name in configured:
        return configured[name]
    return _PAD_DEFAULT_NUMBERS[name]


def _pad_float(name: str) -> float:
    try:
        return float(_pad_config_value(name))
    except (TypeError, ValueError):
        return float(_PAD_DEFAULT_NUMBERS[name])


def _pad_int(name: str) -> int:
    try:
        return int(_pad_config_value(name))
    except (TypeError, ValueError):
        return int(_PAD_DEFAULT_NUMBERS[name])


@dataclass
class PadResult:
    status: str
    trust_confirmed: Optional[bool]
    risk_score: float
    tags: list[str] = field(default_factory=list)
    model_version: str = PAD_MODEL_VERSION
    elapsed_ms: float = 0.0
    deepface_score: float = 0.0
    device_score: float = 0.0
    frame_score: float = 0.0
    quality_penalty: float = 0.0
    device_bg_score: float = 0.0
    frame_global_score: float = 0.0
    recapture_score: float = 0.0
    face_reflection_score: float = 0.0
    color_hist_score: float = 0.0

    def to_update_kwargs(self) -> dict[str, Any]:
        from django.utils import timezone

        return {
            "photo_trust_confirmed": self.trust_confirmed,
            "photo_spoof_status": self.status,
            "photo_spoof_score": self.risk_score,
            "photo_spoof_tags": self.tags,
            "photo_spoof_checked_at": timezone.now(),
            "photo_spoof_model_version": self.model_version,
        }


@dataclass
class DecisionInputs:
    """Inputs for :func:`_decide` (face-gated device/frame, diagnostics, face size)."""

    decode_error: bool
    has_face: bool
    deepface_score: float
    device_score: float
    frame_score: float
    quality_penalty: float
    tags: list[str]
    device_bg_score: float = 0.0
    frame_global_score: float = 0.0
    recapture_score: float = 0.0
    face_area_ratio: float = 0.0
    face_reflection_score: float = 0.0
    color_hist_score: float = 0.0
    model_scores: dict[str, float] = field(default_factory=dict)


def normalize_device(device: Optional[str] = None) -> str:
    """Normalize PAD torch device hint to ``auto``, ``cpu``, or ``cuda``.

    Args:
        device: Optional override; falls back to ``settings.PHOTO_PAD_DEVICE``.

    Returns:
        One of ``DEVICE_AUTO``, ``DEVICE_CPU``, ``DEVICE_CUDA``.
    """
    configured = (
        device or getattr(settings, "PHOTO_PAD_DEVICE", DEVICE_AUTO) or DEVICE_AUTO
    )
    normalized = str(configured).strip().lower()
    if normalized not in DEVICE_VALUES:
        return DEVICE_AUTO
    return normalized


def _resolve_torch_device(preferred_device: str) -> tuple[Optional[Any], str]:
    try:
        import torch
    except Exception:
        return None, DEVICE_CPU

    if preferred_device == DEVICE_CUDA:
        return (
            (
                torch.device("cuda")
                if torch.cuda.is_available()
                else torch.device("cpu")
            ),
            (DEVICE_CUDA if torch.cuda.is_available() else DEVICE_CPU),
        )
    if preferred_device == DEVICE_CPU:
        return torch.device("cpu"), DEVICE_CPU
    if torch.cuda.is_available():
        return torch.device("cuda"), DEVICE_CUDA
    return torch.device("cpu"), DEVICE_CPU


def _downscale_bgr_for_pad(img_bgr: np.ndarray) -> np.ndarray:
    """Downscale large images so PAD detectors run within ``pad_max_long_side``.

    Args:
        img_bgr: Input BGR image.

    Returns:
        Original array if already small enough; otherwise a resized copy.
    """
    max_side = _pad_int("pad_max_long_side")
    h, w = img_bgr.shape[:2]
    m = max(h, w)
    if m <= max_side:
        return img_bgr
    scale = max_side / float(m)
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    return _CV2_RESIZE(img_bgr, (nw, nh), interpolation=_CV2_INTER_AREA)


def _get_fasnet():
    with _runtime_cache_lock:
        if "fasnet" in _runtime_cache:
            return _runtime_cache["fasnet"]
        try:
            import contextlib
            import io

            from deepface.models.spoofing.FasNet import Fasnet
            from monitoring_app.ml_log_quiet import ml_third_party_stdout_verbose

            _stdout_ctx = (
                contextlib.nullcontext()
                if ml_third_party_stdout_verbose()
                else contextlib.redirect_stdout(io.StringIO())
            )
            with _stdout_ctx:
                _runtime_cache["fasnet"] = Fasnet()
        except Exception as exc:
            logger.warning("FasNet is unavailable: %s", exc)
            _runtime_cache["fasnet"] = None
        return _runtime_cache["fasnet"]


def _try_glasses_reflection_mask(img_bgr: np.ndarray) -> Optional[np.ndarray]:
    """Build a dilated eyeglasses mask from face parsing to guard device false positives.

    Args:
        img_bgr: Full BGR frame.

    Returns:
        Single-channel uint8 mask (255 on lenses) or None if unavailable.
    """
    if not bool(getattr(settings, "PHOTO_PAD_GLASSES_REFLECTION_ENABLE", True)):
        return None
    min_px = _pad_int("glasses_mask_min_pixels")
    dil = max(3, _pad_int("glasses_mask_dilate"))
    if dil % 2 == 0:
        dil += 1
    try:
        from monitoring_app import face_parsing

        eng = face_parsing.get_engine()
        if eng is None:
            return None
        rgb = _CV2_CVT_COLOR(img_bgr, _CV2_COLOR_BGR2RGB)
        labels = eng.predict_mask_rgb(rgb)
        g = ((labels == face_parsing.EYEGLASSES_CLASS_ID).astype(np.uint8)) * 255
        if int(np.count_nonzero(g)) < min_px:
            return None
        kernel = _CV2_GET_STRUCTURING_ELEMENT(_CV2_MORPH_ELLIPSE, (dil, dil))
        g = _CV2_DILATE(g, kernel, iterations=1)
        return g
    except Exception as exc:
        logger.debug("PAD glasses reflection mask skipped: %s", exc)
        return None


def _device_box_overlap_glasses_mask(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    mask: np.ndarray,
) -> float:
    """Fraction of a detector box area covered by the glasses mask (0–1)."""
    h, w = mask.shape[:2]
    xi1 = max(0, min(w - 1, int(x1)))
    yi1 = max(0, min(h - 1, int(y1)))
    xi2 = max(xi1 + 1, min(w, int(round(x2))))
    yi2 = max(yi1 + 1, min(h, int(round(y2))))
    roi = mask[yi1:yi2, xi1:xi2]
    box_area = float(max(1, (xi2 - xi1) * (yi2 - yi1)))
    return float(np.count_nonzero(roi > 127)) / box_area


def _guide_model_path(setting_name: str, default_name: str) -> Path:
    """Resolve a PAD guide model path under ``backend/models`` by default."""
    configured = getattr(settings, setting_name, None)
    if configured:
        return Path(str(configured)).expanduser()
    root = getattr(settings, "PHOTO_PAD_GUIDE_MODELS_ROOT", None)
    if root:
        return Path(str(root)).expanduser() / default_name
    return Path(getattr(settings, "BASE_DIR", Path("."))) / "models" / default_name


def _get_guide_face_detector() -> Optional[Any]:
    """Load the OpenCV Caffe SSD face detector used in the Medium guide."""
    cache_key = "guide_face_detector"
    with _runtime_cache_lock:
        if cache_key in _runtime_cache:
            return _runtime_cache[cache_key]
        proto = _guide_model_path(
            "PHOTO_PAD_GUIDE_FACE_DETECTOR_PROTO",
            "deploy.prototxt.txt",
        )
        model = _guide_model_path(
            "PHOTO_PAD_GUIDE_FACE_DETECTOR_MODEL",
            "res10_300x300_ssd_iter_140000.caffemodel",
        )
        if not proto.is_file() or not model.is_file():
            _runtime_cache[cache_key] = None
            return None
        try:
            net = cv2.dnn.readNetFromCaffe(str(proto), str(model))
            _runtime_cache[cache_key] = net
            return net
        except Exception as exc:
            logger.warning("PAD guide Caffe face detector unavailable: %s", exc)
            _runtime_cache[cache_key] = None
            return None


def _get_primary_face_bbox_guide_caffe(
    img_bgr: np.ndarray,
) -> Optional[tuple[int, int, int, int]]:
    """Return the largest face from the guide's OpenCV Caffe SSD detector."""
    net = _get_guide_face_detector()
    if net is None:
        return None
    try:
        h, w = img_bgr.shape[:2]
        blob = cv2.dnn.blobFromImage(
            _CV2_RESIZE(img_bgr, (300, 300)),
            1.0,
            (300, 300),
            (104.0, 117.0, 123.0),
        )
        with _guide_face_detector_infer_lock:
            net.setInput(blob)
            detections = net.forward()
        best_box: Optional[tuple[int, int, int, int]] = None
        best_area = 0.0
        min_conf = _pad_float("guide_face_detector_conf_min")
        for i in range(int(detections.shape[2])):
            conf = float(detections[0, 0, i, 2])
            if conf < min_conf:
                continue
            x1f, y1f, x2f, y2f = detections[0, 0, i, 3:7]
            x1 = max(0, min(w - 1, int(round(float(x1f) * w))))
            y1 = max(0, min(h - 1, int(round(float(y1f) * h))))
            x2 = max(0, min(w - 1, int(round(float(x2f) * w))))
            y2 = max(0, min(h - 1, int(round(float(y2f) * h))))
            bw = max(1, x2 - x1)
            bh = max(1, y2 - y1)
            area = float(bw * bh)
            if area > best_area:
                best_area = area
                best_box = (x1, y1, bw, bh)
        return best_box
    except Exception as exc:
        logger.debug("PAD guide Caffe face detector failed: %s", exc)
        return None


def _get_primary_face_bbox(img_bgr: np.ndarray) -> Optional[tuple[int, int, int, int]]:
    """Return the largest detected face as ``(x, y, w, h)``.

    Args:
        img_bgr: BGR image.

    Returns:
        Bounding box or None if detection fails. ArcFace stays primary; the guide's
        Caffe SSD detector is a fallback and makes the YCrCb/Luv path usable even
        when InsightFace is temporarily unavailable.
    """
    try:
        ml.load_arcface_model()
        arcface_instance = ml.arcface_model_holder.instance
        if arcface_instance is not None:
            faces = arcface_instance.get(img_bgr)
            if faces:
                best = max(
                    faces,
                    key=lambda face: max(0.0, float(face.bbox[2] - face.bbox[0]))
                    * max(0.0, float(face.bbox[3] - face.bbox[1])),
                )
                x1, y1, x2, y2 = [int(v) for v in best.bbox]
                x1 = max(0, x1)
                y1 = max(0, y1)
                x2 = min(img_bgr.shape[1] - 1, x2)
                y2 = min(img_bgr.shape[0] - 1, y2)
                w = max(1, x2 - x1)
                h = max(1, y2 - y1)
                return x1, y1, w, h
    except Exception as exc:
        logger.warning("Face detection failed in PAD: %s", exc)
    return _get_primary_face_bbox_guide_caffe(img_bgr)


def _get_minifasnet_onnx_session() -> Optional[tuple[Any, str, str]]:
    """Load the compatible MiniFASNet ONNX spoof classifier."""
    cache_key = "minifasnet_onnx_session"
    with _runtime_cache_lock:
        if cache_key in _runtime_cache:
            return _runtime_cache[cache_key]

        model_path = _guide_model_path(
            "PHOTO_PAD_MINIFASNET_ONNX_MODEL",
            "minifasnet_v2.onnx",
        )
        if not model_path.is_file():
            _runtime_cache[cache_key] = None
            _runtime_cache["minifasnet_onnx_error"] = "missing"
            return None

        try:
            import onnxruntime as ort

            session = ort.InferenceSession(
                str(model_path),
                providers=["CPUExecutionProvider"],
            )
            input_name = str(session.get_inputs()[0].name)
            output_name = str(session.get_outputs()[0].name)
            _runtime_cache[cache_key] = (session, input_name, output_name)
            _runtime_cache["minifasnet_onnx_error"] = ""
            return _runtime_cache[cache_key]
        except Exception as exc:
            logger.warning("MiniFASNet ONNX PAD model unavailable: %s", exc)
            _runtime_cache[cache_key] = None
            _runtime_cache["minifasnet_onnx_error"] = exc.__class__.__name__
            return None


def _scaled_face_crop_bgr(
    img_bgr: np.ndarray,
    face_bbox: tuple[int, int, int, int],
    scale: float,
) -> Optional[np.ndarray]:
    """Crop a face ROI with the MiniFASNet 2.7x bbox expansion."""
    img_h, img_w = img_bgr.shape[:2]
    x, y, w, h = face_bbox
    if w <= 1 or h <= 1 or img_w <= 1 or img_h <= 1:
        return None

    scale = max(1.0, float(scale))
    cx = float(x) + float(w) * 0.5
    cy = float(y) + float(h) * 0.5
    crop_w = float(w) * scale
    crop_h = float(h) * scale
    x1 = max(0, int(round(cx - crop_w * 0.5)))
    y1 = max(0, int(round(cy - crop_h * 0.5)))
    x2 = min(img_w, int(round(cx + crop_w * 0.5)))
    y2 = min(img_h, int(round(cy + crop_h * 0.5)))
    if x2 <= x1 + 2 or y2 <= y1 + 2:
        return None
    return img_bgr[y1:y2, x1:x2]


def _minifasnet_onnx_input(
    img_bgr: np.ndarray,
    face_bbox: tuple[int, int, int, int],
) -> Optional[np.ndarray]:
    """Build the ONNX input: BGR crop, 80x80, float32 range 0..255, NCHW.

    This checkpoint was trained on raw 0..255 pixel values (no /255
    normalization) — confirmed empirically: with /255 scaling the model
    collapses to one class on almost every input (constant ~0.9997 "fake" on
    live, manually-confirmed-clean faces); feeding 0..255 floats produces a
    confident, image-dependent "real" prediction on those same faces.
    """
    crop = _scaled_face_crop_bgr(
        img_bgr,
        face_bbox,
        _pad_float("minifasnet_onnx_crop_scale"),
    )
    if crop is None or crop.size < 720:
        return None
    resized = _CV2_RESIZE(crop, (80, 80), interpolation=_CV2_INTER_AREA)
    tensor = resized.astype(np.float32)
    tensor = np.transpose(tensor, (2, 0, 1))[None, :, :, :]
    return np.ascontiguousarray(tensor, dtype=np.float32)


def _softmax_probs(values: np.ndarray) -> np.ndarray:
    """Return numerically stable softmax probabilities for one output row."""
    row = np.asarray(values, dtype=np.float64).reshape(-1)
    if row.size == 0:
        return row
    shifted = row - float(np.max(row))
    exp = np.exp(shifted)
    total = float(exp.sum())
    if not np.isfinite(total) or total <= 0.0:
        return np.zeros_like(row, dtype=np.float64)
    return exp / total


def _score_minifasnet_onnx(
    img_bgr: np.ndarray,
    face_bbox: tuple[int, int, int, int],
) -> tuple[Optional[float], list[str]]:
    """Score spoof probability with the compatible MiniFASNet ONNX model."""
    loaded = _get_minifasnet_onnx_session()
    if loaded is None:
        err = str(_runtime_cache.get("minifasnet_onnx_error") or "")
        if err and err != "missing":
            return None, ["minifasnet_onnx_unavailable"]
        return None, []

    session, input_name, output_name = loaded
    tensor = _minifasnet_onnx_input(img_bgr, face_bbox)
    if tensor is None:
        return None, ["minifasnet_onnx_roi_too_small"]

    try:
        raw = np.asarray(session.run([output_name], {input_name: tensor})[0])
        if raw.ndim != 2 or raw.shape[0] < 1 or raw.shape[1] < 3:
            return None, ["minifasnet_onnx_error"]
        row = raw[0].astype(np.float64)
        if (
            np.all(row >= 0.0)
            and np.all(row <= 1.0)
            and abs(float(row.sum()) - 1.0) <= 0.02
        ):
            probs = row
        else:
            probs = _softmax_probs(row)
        if probs.size < 3:
            return None, ["minifasnet_onnx_error"]
        # minivision-ai Silent-Face-Anti-Spoofing class layout: index 1 is
        # "real" (live face), indices 0 and 2 are the two spoof classes
        # (print attack, replay attack) — see upstream test.py: label == 1
        # selects RealFace, anything else is FakeFace.
        spoof_score = float(max(0.0, min(1.0, probs[0] + probs[2])))
        tags = ["minifasnet_onnx_used"]
        if spoof_score >= _pad_float("minifasnet_onnx_mid"):
            tags.append("minifasnet_onnx_elevated")
        if spoof_score >= _pad_float("minifasnet_onnx_strong"):
            tags.append("minifasnet_onnx_fake")
        return spoof_score, tags
    except Exception as exc:
        logger.debug("MiniFASNet ONNX PAD inference failed: %s", exc)
        return None, ["minifasnet_onnx_error"]


def _signal_deepface(
    img_bgr: np.ndarray, face_bbox: Optional[tuple[int, int, int, int]]
) -> tuple[float, list[str], dict[str, float]]:
    """Run model-based anti-spoof signals on the primary face."""
    if face_bbox is None:
        return 0.0, ["no_face"], {}

    score = 0.0
    tags: list[str] = []
    model_scores: dict[str, float] = {}
    model_seen = False

    fasnet = _get_fasnet()
    if fasnet is None:
        tags.append("fasnet_unavailable")
    else:
        try:
            model_seen = True
            is_real, raw_score = fasnet.analyze(img=img_bgr, facial_area=face_bbox)
            fasnet_score = _clamp01(float(raw_score))
            if is_real is False:
                model_scores["fasnet"] = fasnet_score
                tags.append("fasnet_fake")
            else:
                model_scores["fasnet"] = 0.0
                tags.append("fasnet_real")
        except Exception as exc:
            logger.warning("FasNet inference failed: %s", exc)
            tags.append("deepface_error")

    onnx_score, onnx_tags = _score_minifasnet_onnx(img_bgr, face_bbox)
    if onnx_score is not None:
        model_seen = True
        model_scores["minifasnet_onnx"] = _clamp01(onnx_score)
    tags.extend(onnx_tags)

    if not model_seen:
        tags.append("pad_spoof_model_missing")
        return score, tags, model_scores

    if model_scores:
        fasnet_live = "fasnet_real" in tags
        onnx_score = _clamp01(model_scores.get("minifasnet_onnx", 0.0))
        if fasnet_live and "minifasnet_onnx" in model_scores:
            score = 0.0
            if onnx_score >= _pad_float("spoof_model_disagreement_min"):
                tags.append("spoof_model_disagreement")
                tags.append("minifasnet_onnx_advisory_when_fasnet_real")
        else:
            values = list(model_scores.values())
            score = _clamp01(sum(values) / float(len(values)))
            spread = max(values) - min(values)
            if spread >= _pad_float("spoof_model_disagreement_min"):
                tags.append("spoof_model_disagreement")
        if score >= _pad_float("spoof_model_family_mid"):
            tags.append("spoof_model_family_elevated")
        if score >= _pad_float("spoof_model_family_strong"):
            tags.append("spoof_model_family_fake")
    return score, tags, model_scores


def _get_device_detector(
    preferred_device: str,
) -> tuple[Optional[Any], Optional[Any], str]:
    cache_key = f"detector:{preferred_device}"
    with _runtime_cache_lock:
        if cache_key in _runtime_cache:
            model, torch_module, resolved = _runtime_cache[cache_key]
            return model, torch_module, resolved

        torch_device, resolved = _resolve_torch_device(preferred_device)
        if torch_device is None:
            _runtime_cache[cache_key] = (None, None, DEVICE_CPU)
            return None, None, DEVICE_CPU

        try:
            import torch
            import torchvision.models.detection as detection_models

            model = detection_models.fasterrcnn_mobilenet_v3_large_320_fpn(
                weights=detection_models.FasterRCNN_MobileNet_V3_Large_320_FPN_Weights.DEFAULT
            )
            model.to(torch_device)
            model.eval()
            _runtime_cache[cache_key] = (model, torch, resolved)
            return model, torch, resolved
        except Exception as exc:
            logger.warning("Device detector unavailable: %s", exc)
            _runtime_cache[cache_key] = (None, None, resolved)
            return None, None, resolved


def _signal_device(
    img_bgr: np.ndarray,
    preferred_device: str,
    face_bbox: Optional[tuple[int, int, int, int]],
    glasses_mask: Optional[np.ndarray] = None,
) -> tuple[float, float, list[str]]:
    """Score COCO device boxes split into on-face vs background-only evidence.

    Returns:
        ``(best_on_face_score, best_background_score, sorted_tags)``.
    """
    model, torch_module, _resolved_device = _get_device_detector(preferred_device)
    if model is None or torch_module is None:
        return 0.0, 0.0, []

    try:
        import torchvision.transforms.functional as tvf

        rgb = _CV2_CVT_COLOR(img_bgr, _CV2_COLOR_BGR2RGB)
        tensor = tvf.to_tensor(rgb)
        model_device = next(model.parameters()).device
        tensor = tensor.to(model_device)

        with torch_module.no_grad():
            outputs = model([tensor])[0]

        scores = outputs["scores"].detach().cpu().tolist()
        labels = outputs["labels"].detach().cpu().tolist()
        boxes = outputs["boxes"].detach().cpu().tolist()

        height, width = img_bgr.shape[:2]
        frame_area = max(1.0, float(height * width))
        tags: list[str] = []
        best_face = 0.0
        best_bg = 0.0
        exp_scale = _pad_float("device_face_expand_scale")
        diou_min = _pad_float("device_face_iou_min")
        dcover_min = _pad_float("device_face_cover_ratio_min")

        skip_ov = _pad_float("glasses_device_overlap_skip")
        soft_ov = _pad_float("glasses_device_overlap_soft")

        for label, confidence, box in zip(labels, scores, boxes):
            if label not in _COCO_DEVICE_CLASSES:
                continue
            if confidence < _pad_float("device_min_conf"):
                continue
            x1, y1, x2, y2 = box
            glasses_ov = 0.0
            if glasses_mask is not None:
                glasses_ov = _device_box_overlap_glasses_mask(
                    x1, y1, x2, y2, glasses_mask
                )
                if glasses_ov >= skip_ov:
                    tags.append("device_ignored_glasses_reflection")
                    continue
            area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
            ratio = area / frame_area
            if ratio < _pad_float("device_min_area_ratio"):
                continue
            device_name = _COCO_DEVICE_CLASSES[label]
            ratio_factor = min(1.0, ratio / _pad_float("device_ratio_ref"))
            confidence_factor = min(1.0, confidence)
            candidate = min(
                1.0,
                _pad_float("device_score_conf_weight") * confidence_factor
                + _pad_float("device_score_ratio_weight") * ratio_factor,
            )
            if glasses_mask is not None and glasses_ov >= soft_ov and skip_ov > soft_ov:
                damp = 1.0 - (glasses_ov - soft_ov) / (skip_ov - soft_ov)
                candidate *= max(0.12, min(1.0, damp))

            rel, _gate_reason = device_presentation_relevant(
                face_bbox,
                (float(x1), float(y1), float(x2), float(y2)),
                width,
                height,
                expand_scale=exp_scale,
                iou_min=diou_min,
                cover_ratio_min=dcover_min,
            )
            if rel:
                tags.append(f"device_on_face:{device_name}")
                best_face = max(best_face, candidate)
            else:
                tags.append(f"device_background:{device_name}")
                best_bg = max(best_bg, candidate)

        return best_face, best_bg, sorted(set(tags))
    except Exception as exc:
        logger.warning("Device detector inference failed: %s", exc)
        return 0.0, 0.0, []


def _frame_scores_from_edges(
    edges: np.ndarray,
    frame_area: float,
    w: int,
    h: int,
    face_bbox: Optional[tuple[int, int, int, int]],
    face_center: Optional[tuple[float, float]],
) -> tuple[float, float]:
    """Compute global vs face-gated quad scores from a Canny edge map.

    Args:
        edges: Binary edge image.
        frame_area: Full-frame area for normalization.
        w: Image width.
        h: Image height.
        face_bbox: Primary face ``(x, y, w, h)`` or None.
        face_center: Face center in pixel coordinates or None.

    Returns:
        ``(best_face_gated_score, best_global_score)``. Only the first value is used
        for spoof decisions; the second is diagnostic (background rectangles).
    """
    dilate_kernel = max(1, _pad_int("frame_dilate_kernel"))
    kernel = _CV2_GET_STRUCTURING_ELEMENT(
        _CV2_MORPH_RECT,
        (dilate_kernel, dilate_kernel),
    )
    edges = _CV2_DILATE(edges, kernel, iterations=1)
    contours, _ = _CV2_FIND_CONTOURS(
        edges,
        _CV2_RETR_EXTERNAL,
        _CV2_CHAIN_APPROX_SIMPLE,
    )
    best_global = 0.0
    best_face = 0.0
    f_exp = _pad_float("frame_face_expand_scale")
    fiou_min = _pad_float("frame_face_iou_min")
    max_quad_ar = _pad_float("frame_face_max_quad_area_ratio")
    large_cover_min = _pad_float("frame_face_min_cover_when_large_quad")
    face_xy_for_cover: Optional[tuple[float, float, float, float]] = None
    face_area_px = 1.0
    if face_bbox is not None:
        face_xy_for_cover = face_bbox_to_xyxy(face_bbox, w, h)
        fx1, fy1, fx2, fy2 = face_xy_for_cover
        face_area_px = max(1.0, (fx2 - fx1) * (fy2 - fy1))
    for contour in contours:
        area = _CV2_CONTOUR_AREA(contour)
        area_ratio = area / frame_area
        if area_ratio < _pad_float("frame_min_area_ratio"):
            continue
        perimeter = _CV2_ARC_LENGTH(contour, True)
        approx = _CV2_APPROX_POLY_DP(
            contour,
            _pad_float("frame_poly_epsilon") * perimeter,
            True,
        )
        if len(approx) != 4:
            continue
        x, y, bw, bh = _CV2_BOUNDING_RECT(approx)
        rect_area = float(max(1, bw * bh))
        solidity = float(area) / rect_area
        if solidity < _pad_float("frame_min_solidity"):
            continue
        base = min(1.0, area_ratio / _pad_float("frame_ratio_ref"))
        face_inside = False
        if face_center is not None:
            cx, cy = face_center
            face_inside = bool(x <= cx <= (x + bw) and y <= cy <= (y + bh))
        border_margin = _pad_int("frame_border_margin_px")
        near_borders = (
            (x <= border_margin)
            or (y <= border_margin)
            or ((x + bw) >= w - border_margin)
            or ((y + bh) >= h - border_margin)
        )
        cand_g = base
        if face_inside:
            cand_g = min(1.0, cand_g + _pad_float("frame_face_bonus"))
        if near_borders:
            cand_g = min(1.0, cand_g + _pad_float("frame_border_bonus"))
        best_global = max(best_global, cand_g)

        rel, _ = frame_quad_face_relevant(
            face_bbox,
            int(x),
            int(y),
            int(bw),
            int(bh),
            w,
            h,
            expand_scale=f_exp,
            iou_min=fiou_min,
        )
        if rel and face_xy_for_cover is not None and area_ratio > max_quad_ar:
            qxy = (float(x), float(y), float(x + bw), float(y + bh))
            cover = intersection_area_xyxy(face_xy_for_cover, qxy) / face_area_px
            if cover < large_cover_min:
                rel = False
        if not rel:
            continue
        cand_f = base
        if face_inside:
            cand_f = min(1.0, cand_f + _pad_float("frame_face_bonus"))
        if near_borders and rel:
            cand_f = min(1.0, cand_f + _pad_float("frame_border_bonus"))
        best_face = max(best_face, cand_f)
    return best_face, best_global


def _signal_screen_frame(
    img_bgr: np.ndarray,
    face_bbox: Optional[tuple[int, int, int, int]],
    glasses_mask: Optional[np.ndarray] = None,
) -> tuple[float, float, list[str]]:
    """Detect quad-like screen edges; split face-gated vs global (diagnostic) scores."""
    h, w = img_bgr.shape[:2]
    frame_area = float(max(1, h * w))
    face_center = None
    if face_bbox is not None:
        x, y, fw, fh = face_bbox
        face_center = (x + fw / 2.0, y + fh / 2.0)

    gray = _CV2_CVT_COLOR(img_bgr, _CV2_COLOR_BGR2GRAY)
    gaussian_kernel = max(3, _pad_int("frame_gaussian_kernel"))
    if gaussian_kernel % 2 == 0:
        gaussian_kernel += 1
    blurred = _CV2_GAUSSIAN_BLUR(gray, (gaussian_kernel, gaussian_kernel), 0)
    canny_low = _pad_int("frame_canny_low")
    canny_high = _pad_int("frame_canny_high")
    edges = _CV2_CANNY(blurred, canny_low, canny_high)
    if glasses_mask is not None and glasses_mask.shape[:2] == (h, w):
        edges = np.asarray(edges).copy()
        edges[glasses_mask > 127] = 0
    best_face, best_global = _frame_scores_from_edges(
        edges, frame_area, w, h, face_bbox, face_center
    )
    bezel_score = _signal_dark_bezel_context(gray)
    best_global = max(best_global, bezel_score)

    brightness = float(gray.mean())
    if _CV2_CREATE_CLAHE is not None and (brightness < 70.0 or brightness > 180.0):
        try:
            clahe_obj = _CV2_CREATE_CLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray_enhanced = clahe_obj.apply(gray)
            blurred_enh = _CV2_GAUSSIAN_BLUR(
                gray_enhanced, (gaussian_kernel, gaussian_kernel), 0
            )
            edges_enh = _CV2_CANNY(blurred_enh, max(20, canny_low - 25), canny_high)
            if glasses_mask is not None and glasses_mask.shape[:2] == (h, w):
                edges_enh = np.asarray(edges_enh).copy()
                edges_enh[glasses_mask > 127] = 0
            sf, sg = _frame_scores_from_edges(
                edges_enh, frame_area, w, h, face_bbox, face_center
            )
            best_face = max(best_face, sf)
            best_global = max(best_global, sg)
        except Exception as exc:
            logger.debug("PAD CLAHE frame fallback failed: %s", exc)

    tags_out: list[str] = []
    th = _pad_float("frame_tag_threshold")
    if bezel_score >= max(0.18, th * 0.7):
        tags_out.append("screen_bezel_context")
    if best_face >= th:
        tags_out.append("screen_frame_face")
    if best_global >= th and best_face < th:
        tags_out.append("screen_frame_background_only")
    if best_face >= th or best_global >= th:
        if glasses_mask is not None:
            tags_out.append("frame_edges_masked_glasses")
    return best_face, best_global, tags_out


def _signal_dark_bezel_context(gray: np.ndarray) -> float:
    """Estimate whole-frame dark-bezel context for screen-photo captures.

    Args:
        gray: Full grayscale image.

    Returns:
        Score in ``[0, 1]`` for dark, fairly uniform border strips around brighter
        interior content.
    """
    h, w = gray.shape[:2]
    if h < 120 or w < 90:
        return 0.0

    pad_y = max(8, int(round(h * 0.08)))
    pad_x = max(6, int(round(w * 0.045)))
    if (h - 2 * pad_y) < 32 or (w - 2 * pad_x) < 32:
        return 0.0

    center = gray[pad_y : h - pad_y, pad_x : w - pad_x]
    center_mean = float(center.mean())
    if center_mean < 45.0:
        return 0.0

    top = gray[:pad_y, :]
    bottom = gray[h - pad_y :, :]
    left = gray[:, :pad_x]
    right = gray[:, w - pad_x :]

    def _strip_score(strip: np.ndarray) -> float:
        strip_mean = float(strip.mean())
        strip_std = float(strip.std())
        darkness = max(0.0, (center_mean - strip_mean - 12.0) / 70.0)
        black_ratio = float(np.mean(strip < min(72.0, center_mean * 0.58)))
        uniform = max(0.0, 1.0 - min(1.0, strip_std / 46.0))
        return min(1.0, 0.5 * darkness + 0.3 * black_ratio + 0.2 * uniform)

    top_score = _strip_score(top)
    bottom_score = _strip_score(bottom)
    left_score = _strip_score(left)
    right_score = _strip_score(right)
    horizontal_pair = min(top_score, bottom_score)
    vertical_pair = min(left_score, right_score)
    pair_score = max(horizontal_pair, vertical_pair)
    single_bar_score = 0.0
    horiz_single_support = max(top_score, bottom_score)
    horiz_side_support = min(left_score, right_score)
    row_mean = gray.mean(axis=1)
    lower_jump = 0.0
    if h >= 16:
        lower_jump = float(np.abs(np.diff(row_mean[int(h * 0.6) :])).max()) / max(
            1.0, center_mean
        )
    if (
        horiz_single_support >= 0.72
        and horiz_side_support >= 0.06
        and lower_jump >= 0.1
    ):
        single_bar_score = min(
            1.0,
            (
                0.68 * horiz_single_support
                + 0.16 * horiz_side_support
                + 0.16 * lower_jump
            )
            * 0.58,
        )
    final_score = max(pair_score, single_bar_score)
    if final_score < 0.2:
        return 0.0
    return min(1.0, final_score)


def _signal_recapture(
    img_bgr: np.ndarray, face_bbox: Optional[tuple[int, int, int, int]]
) -> tuple[float, list[str]]:
    """Face-inner recapture / periodicity cue (blur-gated, dual-channel agreement)."""
    return signal_recapture_face_roi(
        img_bgr,
        face_bbox,
        inner_face_scale=_pad_float("recapture_inner_face_scale"),
        fft_ring_inner=_pad_int("recapture_fft_ring_inner"),
        fft_ring_outer=_pad_int("recapture_fft_ring_outer"),
        fft_baseline=_pad_float("recapture_fft_baseline"),
        fft_scale=_pad_float("recapture_fft_scale"),
        sobel_aniso_min=_pad_float("recapture_sobel_aniso_min"),
        sobel_aniso_scale=_pad_float("recapture_sobel_aniso_scale"),
        min_laplacian_var=_pad_float("recapture_min_laplacian_var"),
        blur_dampen_factor=_pad_float("recapture_blur_dampen_factor"),
    )


def _signal_face_reflection(
    img_bgr: np.ndarray,
    face_bbox: Optional[tuple[int, int, int, int]],
) -> tuple[float, list[str]]:
    """Detect screen-like specular patches on the upper face.

    The signal is intentionally corroborative: it finds clipped white/colored
    highlights and small rectangular glints around the eye band, but the decision
    engine only treats it as spoof evidence when another PAD channel also agrees.
    """
    if face_bbox is None:
        return 0.0, []

    x, y, fw, fh = face_bbox
    if fw < 28 or fh < 28:
        return 0.0, []

    ih, iw = img_bgr.shape[:2]
    x1 = max(0, int(round(x + 0.10 * fw)))
    x2 = min(iw, int(round(x + 0.90 * fw)))
    y1 = max(0, int(round(y + 0.16 * fh)))
    y2 = min(ih, int(round(y + 0.58 * fh)))
    if x2 <= x1 + 8 or y2 <= y1 + 8:
        return 0.0, []

    roi = img_bgr[y1:y2, x1:x2]
    if roi.size < 240:
        return 0.0, []

    hsv = _CV2_CVT_COLOR(roi, _CV2_COLOR_BGR2HSV)
    gray = _CV2_CVT_COLOR(roi, _CV2_COLOR_BGR2GRAY)
    sat = hsv[:, :, 1].astype(np.float32)
    val = hsv[:, :, 2].astype(np.float32)
    v_mean = float(val.mean())
    v_std = float(val.std())

    white_v_min = max(_pad_float("reflection_white_v_min"), v_mean + 1.15 * v_std)
    white_mask = (val >= white_v_min) & (sat <= _pad_float("reflection_white_s_max"))
    color_mask = (val >= _pad_float("reflection_color_v_min")) & (
        sat >= _pad_float("reflection_color_s_min")
    )
    clipped_mask = val >= 248.0
    mask = white_mask | color_mask | clipped_mask

    area = float(max(1, mask.size))
    highlight_ratio = float(np.count_nonzero(mask)) / area
    clipped_ratio = float(np.count_nonzero(clipped_mask)) / area
    color_ratio = float(np.count_nonzero(color_mask)) / area

    comp_best = 0.0
    mask_u8 = (mask.astype(np.uint8)) * 255
    try:
        n_labels, _labels, stats, _centroids = _CV2_CONNECTED_COMPONENTS_WITH_STATS(
            mask_u8,
            8,
        )
        min_ar = _pad_float("reflection_component_min_area_ratio")
        max_ar = _pad_float("reflection_component_max_area_ratio")
        for label_idx in range(1, int(n_labels)):
            c_area = float(stats[label_idx, 4])
            area_ratio = c_area / area
            if area_ratio < min_ar or area_ratio > max_ar:
                continue
            cw = float(max(1, stats[label_idx, 2]))
            ch = float(max(1, stats[label_idx, 3]))
            rectness = min(1.0, c_area / max(1.0, cw * ch))
            aspect = max(cw, ch) / max(1.0, min(cw, ch))
            aspect_score = min(1.0, max(0.0, (aspect - 1.15) / 2.7))
            size_score = min(1.0, area_ratio / 0.018)
            comp_best = max(
                comp_best,
                0.42 * size_score + 0.30 * rectness + 0.28 * aspect_score,
            )
    except Exception as exc:
        logger.debug("PAD face reflection connected components skipped: %s", exc)

    edge_density = 0.0
    if np.count_nonzero(mask_u8) > 0:
        try:
            edges = _CV2_CANNY(gray, 60, 170)
            edge_density = float(np.mean(edges[mask_u8 > 0] > 0))
        except Exception:
            edge_density = 0.0

    ratio_score = min(1.0, highlight_ratio / 0.052)
    clipped_score = min(1.0, clipped_ratio / 0.016)
    color_score = min(1.0, color_ratio / 0.022)
    edge_score = min(1.0, edge_density / 0.22) if edge_density > 0.0 else 0.0
    score = max(
        comp_best,
        0.58 * ratio_score + 0.24 * clipped_score + 0.18 * edge_score,
        0.78 * color_score + 0.22 * edge_score,
    )
    score = float(max(0.0, min(1.0, score)))

    tags: list[str] = []
    if score >= _pad_float("reflection_review_min"):
        tags.append("face_reflection_elevated")
    if score >= _pad_float("reflection_mid"):
        tags.append("face_reflection_screen_like")
    if comp_best >= 0.35:
        tags.append("face_rectangular_reflection")
    if color_score >= 0.35:
        tags.append("face_colored_screen_reflection")
    if clipped_score >= 0.35:
        tags.append("face_clipped_specular_reflection")
    return score, tags


def _face_inner_roi_bgr(
    img_bgr: np.ndarray,
    face_bbox: tuple[int, int, int, int],
    scale: float,
) -> Optional[np.ndarray]:
    """Crop a central face ROI, clipped to image bounds."""
    x, y, fw, fh = face_bbox
    if fw < 24 or fh < 24:
        return None
    ih, iw = img_bgr.shape[:2]
    sc = max(0.35, min(1.0, float(scale)))
    cx = float(x) + 0.5 * float(fw)
    cy = float(y) + 0.52 * float(fh)
    rw = max(8, int(round(float(fw) * sc)))
    rh = max(8, int(round(float(fh) * sc)))
    x1 = max(0, int(round(cx - 0.5 * rw)))
    y1 = max(0, int(round(cy - 0.5 * rh)))
    x2 = min(iw, int(round(cx + 0.5 * rw)))
    y2 = min(ih, int(round(cy + 0.5 * rh)))
    if x2 <= x1 + 8 or y2 <= y1 + 8:
        return None
    return img_bgr[y1:y2, x1:x2]


def _channel_hist_metrics(
    channel: np.ndarray, bins: int = 64
) -> tuple[float, float, float]:
    """Return normalized entropy, top-bin mass, and occupied-bin ratio."""
    hist, _edges = np.histogram(channel.ravel(), bins=bins, range=(0, 256))
    total = float(hist.sum())
    if total <= 0.0:
        return 1.0, 0.0, 1.0
    p = hist.astype(np.float64) / total
    nz = p[p > 0.0]
    entropy = float(-(nz * np.log(nz)).sum() / np.log(float(bins)))
    top_mass = float(np.sort(p)[-4:].sum())
    occupied = float(np.count_nonzero(hist >= max(2.0, total * 0.001))) / float(bins)
    return entropy, top_mass, occupied


def _guide_calc_hist(img: np.ndarray) -> np.ndarray:
    """Guide-compatible 3-channel histogram normalized to the 0..255 range."""
    histograms: list[np.ndarray] = []
    for channel_idx in range(3):
        hist = cv2.calcHist([img], [channel_idx], None, [256], [0, 256])
        hmax = float(hist.max())
        if hmax > 1e-9:
            hist = hist * (255.0 / hmax)
        histograms.append(hist)
    return np.asarray(histograms)


def _guide_color_feature_vector(face_roi_bgr: np.ndarray) -> np.ndarray:
    """Build the exact YCrCb+Luv feature vector used by the guide model."""
    img_ycrcb = _CV2_CVT_COLOR(face_roi_bgr, _CV2_COLOR_BGR2YCrCb)
    img_luv = _CV2_CVT_COLOR(face_roi_bgr, _CV2_COLOR_BGR2Luv)
    ycrcb_hist = _guide_calc_hist(img_ycrcb)
    luv_hist = _guide_calc_hist(img_luv)
    feature_vector = np.append(ycrcb_hist.ravel(), luv_hist.ravel())
    return feature_vector.reshape(1, int(feature_vector.shape[0]))


def _install_sklearn_019_pickle_aliases(joblib_module: Any) -> None:
    """Map old sklearn 0.19 pickle module paths to current sklearn modules."""
    try:
        import sys

        import joblib.numpy_pickle as numpy_pickle
        import sklearn.ensemble._forest as forest_mod
        import sklearn.tree._classes as tree_classes_mod

        sys.modules.setdefault("sklearn.ensemble.forest", forest_mod)
        sys.modules.setdefault("sklearn.tree.tree", tree_classes_mod)
        sys.modules.setdefault("sklearn.externals.joblib", joblib_module)
        sys.modules.setdefault("sklearn.externals.joblib.numpy_pickle", numpy_pickle)
    except Exception as exc:
        logger.debug("PAD guide sklearn pickle aliases skipped: %s", exc)


def _patch_sklearn_tree_unpickle_compat() -> Any:
    """Allow unpickling sklearn 0.19 trees into sklearn 1.5+ runtime."""
    import sklearn.tree._tree as tree_mod

    cache_key = "guide_sklearn_tree_unpickle_patch"
    with _runtime_cache_lock:
        if cache_key in _runtime_cache:
            return _runtime_cache[cache_key]

        original_check = tree_mod._check_node_ndarray

        def _relaxed_check(node_ndarray: Any, expected_dtype: Any = None) -> Any:
            try:
                return original_check(node_ndarray, expected_dtype=expected_dtype)
            except ValueError:
                names = list(getattr(node_ndarray, "dtype", None).names or [])
                if (
                    "missing_go_to_left" not in names
                    and expected_dtype is not None
                    and hasattr(node_ndarray, "shape")
                ):
                    upgraded = np.zeros(node_ndarray.shape, dtype=expected_dtype)
                    for field in names:
                        upgraded[field] = node_ndarray[field]
                    return upgraded
                return node_ndarray

        tree_mod._check_node_ndarray = _relaxed_check
        _runtime_cache[cache_key] = original_check
        return original_check


def _guide_model_modern_path(legacy_path: Path) -> Path:
    """Path for a sklearn 1.5+ compatible re-export of a legacy guide model."""
    return legacy_path.parent / f"{legacy_path.stem}.sklearn15.joblib"


def _load_guide_extra_trees_classifier(model_path: Path) -> Any:
    """Load guide ExtraTrees: prefer modern export, else migrate legacy pickle."""
    import warnings

    import joblib

    modern_path = _guide_model_modern_path(model_path)
    if modern_path.is_file():
        return joblib.load(str(modern_path))

    if not model_path.is_file():
        raise FileNotFoundError(str(model_path))

    _install_sklearn_019_pickle_aliases(joblib)
    _patch_sklearn_tree_unpickle_compat()
    try:
        from sklearn.exceptions import InconsistentVersionWarning
    except Exception:
        InconsistentVersionWarning = UserWarning
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=InconsistentVersionWarning)
        model = joblib.load(str(model_path))
    if not callable(getattr(model, "predict", None)):
        raise RuntimeError("loaded object has no predict")
    try:
        joblib.dump(model, str(modern_path))
        logger.info("PAD guide model migrated to %s", modern_path)
    except Exception as exc:
        logger.warning("PAD guide model migration save failed: %s", exc)
    return model


def _guide_extra_trees_spoof_score(model: Any, feature_vector: np.ndarray) -> float:
    """Spoof probability from guide ExtraTrees (handles legacy exports)."""
    row = np.asarray(feature_vector, dtype=np.float64)
    if row.ndim == 1:
        row = row.reshape(1, -1)
    try:
        probs = np.asarray(model.predict_proba(row), dtype=np.float64)
    except Exception:
        probs = None
    if probs is not None and probs.ndim == 2 and probs.shape[0] >= 1:
        total = float(probs[0].sum())
        if 0.99 <= total <= 1.01:
            classes = list(getattr(model, "classes_", []))
            if 1 in classes:
                spoof_idx = int(classes.index(1))
            else:
                spoof_idx = 1 if probs.shape[1] > 1 else 0
            return float(max(0.0, min(1.0, probs[0, spoof_idx])))
    estimators = list(getattr(model, "estimators_", []) or [])
    if estimators:
        votes = np.asarray(
            [int(est.predict(row)[0]) for est in estimators],
            dtype=np.int8,
        )
        return float(np.mean(votes == 1))
    return float(int(model.predict(row)[0]) == 1)


def _get_guide_color_model() -> Optional[Any]:
    """Load the guide's YCrCb+Luv ExtraTrees pickle when sklearn can read it."""
    cache_key = "guide_ycrcb_luv_extra_trees"
    with _runtime_cache_lock:
        if cache_key in _runtime_cache:
            return _runtime_cache[cache_key]
        model_path = _guide_model_path(
            "PHOTO_PAD_GUIDE_COLOR_MODEL",
            "replay-attack_ycrcb_luv_extraTreesClassifier.pkl",
        )
        try:
            model = _load_guide_extra_trees_classifier(model_path)
            _runtime_cache[cache_key] = model
            _runtime_cache["guide_ycrcb_luv_model_error"] = ""
            return model
        except FileNotFoundError:
            _runtime_cache[cache_key] = None
            _runtime_cache["guide_ycrcb_luv_model_error"] = "missing"
            return None
        except Exception as exc:
            logger.warning(
                "PAD guide YCrCb/Luv ExtraTrees model unavailable: %s. "
                "The bundled model was trained with sklearn 0.19.1; keeping "
                "heuristic YCrCb/Luv fallback active.",
                exc,
            )
            _runtime_cache[cache_key] = None
            _runtime_cache["guide_ycrcb_luv_model_error"] = exc.__class__.__name__
            return None


def _score_guide_color_model(face_roi_bgr: np.ndarray) -> tuple[Optional[float], list[str]]:
    """Score face ROI with the guide's pretrained ExtraTrees model if loadable."""
    model = _get_guide_color_model()
    if model is None:
        err = str(_runtime_cache.get("guide_ycrcb_luv_model_error") or "")
        if err and err != "missing":
            return None, ["guide_ycrcb_luv_model_unavailable"]
        return None, []
    try:
        fv = _guide_color_feature_vector(face_roi_bgr)
        score = _guide_extra_trees_spoof_score(model, fv)
        tags: list[str] = ["guide_ycrcb_luv_model_used"]
        if score >= _pad_float("guide_color_model_mid"):
            tags.append("guide_ycrcb_luv_model_elevated")
        if score >= _pad_float("guide_color_model_strong"):
            tags.append("guide_ycrcb_luv_model_fake")
        return score, tags
    except Exception as exc:
        logger.debug("PAD guide YCrCb/Luv model inference failed: %s", exc)
        return None, ["guide_ycrcb_luv_model_error"]


def _signal_color_histogram(
    img_bgr: np.ndarray,
    face_bbox: Optional[tuple[int, int, int, int]],
    face_area_ratio: float,
) -> tuple[float, list[str]]:
    """Color-space histogram cue inspired by the YCrCb/Luv PAD method.

    The Medium article uses concatenated YCrCb and Luv histograms with a trained
    classifier. Here the same color spaces are used as a conservative heuristic:
    the score rises only when chroma histograms are concentrated/sparse or when
    luminance varies while chroma stays implausibly flat. The decision engine
    treats this as corroboration, not as standalone proof.
    """
    if face_bbox is None:
        return 0.0, []
    min_face = _pad_float("color_hist_min_face_area_ratio")
    if face_area_ratio > 1e-9 and face_area_ratio < min_face:
        return 0.0, []

    roi = _face_inner_roi_bgr(
        img_bgr,
        face_bbox,
        _pad_float("color_hist_inner_face_scale"),
    )
    if roi is None or roi.size < 720:
        return 0.0, []

    guide_score, guide_tags = _score_guide_color_model(roi)

    try:
        roi_small = _CV2_RESIZE(roi, (128, 128), interpolation=_CV2_INTER_AREA)
        ycrcb = _CV2_CVT_COLOR(roi_small, _CV2_COLOR_BGR2YCrCb)
        luv = _CV2_CVT_COLOR(roi_small, _CV2_COLOR_BGR2Luv)
    except Exception as exc:
        logger.debug("PAD color histogram signal skipped: %s", exc)
        return 0.0, []

    chroma_channels = [
        ycrcb[:, :, 1],
        ycrcb[:, :, 2],
        luv[:, :, 1],
        luv[:, :, 2],
    ]
    metrics = [_channel_hist_metrics(ch) for ch in chroma_channels]
    entropy = float(np.mean([m[0] for m in metrics]))
    peak_mass = float(np.mean([m[1] for m in metrics]))
    occupancy = float(np.mean([m[2] for m in metrics]))

    low_entropy = max(
        0.0,
        (_pad_float("color_hist_low_entropy_ref") - entropy)
        / max(1e-6, _pad_float("color_hist_low_entropy_ref")),
    )
    peak_score = max(
        0.0,
        (peak_mass - _pad_float("color_hist_peak_mass_ref"))
        / max(1e-6, 0.82 - _pad_float("color_hist_peak_mass_ref")),
    )
    sparse_score = max(
        0.0,
        (_pad_float("color_hist_sparse_occupancy_ref") - occupancy)
        / max(1e-6, _pad_float("color_hist_sparse_occupancy_ref")),
    )

    y_std = float(ycrcb[:, :, 0].std())
    l_std = float(luv[:, :, 0].std())
    luma_std = 0.5 * (y_std + l_std)
    chroma_std = float(np.mean([float(ch.std()) for ch in chroma_channels]))
    flat_chroma = max(
        0.0,
        (_pad_float("color_hist_flat_chroma_std") - chroma_std)
        / max(1e-6, _pad_float("color_hist_flat_chroma_std")),
    )
    luma_support = max(
        0.0,
        min(
            1.0,
            (luma_std - _pad_float("color_hist_luma_std_min")) / 34.0,
        ),
    )
    mismatch = flat_chroma * luma_support

    score = (
        0.34 * min(1.0, peak_score)
        + 0.28 * min(1.0, sparse_score)
        + 0.24 * min(1.0, low_entropy)
        + 0.14 * min(1.0, mismatch)
    )
    feat_min = _pad_float("color_hist_strong_feature_min")
    strong_feature_count = sum(
        1
        for value in (peak_score, sparse_score, low_entropy, mismatch)
        if value >= feat_min
    )
    full_feats = _pad_int("color_hist_full_score_features_min")
    if strong_feature_count < 2:
        score *= 0.40
    elif strong_feature_count < full_feats:
        score *= 0.78
    score = float(max(0.0, min(1.0, score)))
    if guide_score is not None:
        score = max(score, guide_score)
    else:
        score *= _pad_float("color_hist_heuristic_only_scale")

    tags: list[str] = list(guide_tags)
    if score >= _pad_float("color_hist_mid"):
        tags.append("face_color_histogram_elevated")
    if score >= _pad_float("color_hist_strong"):
        tags.append("face_color_histogram_screen_like")
    if peak_score >= 0.45:
        tags.append("face_color_histogram_concentrated_chroma")
    if sparse_score >= 0.45:
        tags.append("face_color_histogram_sparse_chroma")
    if mismatch >= 0.45:
        tags.append("face_color_luma_chroma_mismatch")
    return score, tags


def _face_bbox_is_edge_cropped(
    face_bbox: Optional[tuple[int, int, int, int]],
    img_w: int,
    img_h: int,
) -> bool:
    """Return whether the detected face is clipped too tightly by the frame edge."""
    if face_bbox is None:
        return False
    x, y, fw, fh = face_bbox
    margin_x = max(6, int(fw * 0.12))
    margin_y = max(6, int(fh * 0.12))
    return bool(
        x <= margin_x
        or y <= margin_y
        or (x + fw) >= img_w - margin_x
        or (y + fh) >= img_h - margin_y
    )


def _signal_quality(
    img_bgr: np.ndarray, face_bbox: Optional[tuple[int, int, int, int]]
) -> tuple[float, list[str]]:
    """Heuristic quality penalty (blur, exposure, contrast, face size)."""
    gray = _CV2_CVT_COLOR(img_bgr, _CV2_COLOR_BGR2GRAY)
    blur_var = float(_CV2_LAPLACIAN(gray, _CV2_CV_64F).var())
    brightness = float(gray.mean())
    contrast = float(gray.std())

    frame_area = float(max(1, img_bgr.shape[0] * img_bgr.shape[1]))
    face_ratio = 0.0
    if face_bbox is not None:
        _x, _y, fw, fh = face_bbox
        face_ratio = float(max(1, fw * fh)) / frame_area

    penalty = 0.0
    tags: list[str] = []

    if blur_var < _pad_float("quality_blur_min"):
        penalty += _pad_float("quality_penalty_blur")
        tags.append("quality_blur")
    if brightness < _pad_float("quality_brightness_min") or brightness > _pad_float(
        "quality_brightness_max"
    ):
        penalty += _pad_float("quality_penalty_exposure")
        tags.append("quality_exposure")
    if contrast < _pad_float("quality_contrast_min"):
        penalty += _pad_float("quality_penalty_contrast")
        tags.append("quality_low_contrast")
    if face_bbox is not None and face_ratio < _pad_float("quality_face_ratio_min"):
        penalty += _pad_float("quality_penalty_small_face")
        tags.append("quality_small_face")
    if _face_bbox_is_edge_cropped(face_bbox, img_bgr.shape[1], img_bgr.shape[0]):
        penalty += _pad_float("quality_penalty_small_face") * 0.5
        tags.append("quality_face_edge_crop")

    penalty = min(1.0, penalty)
    if penalty >= _pad_float("quality_poor_threshold"):
        tags.append("quality_poor")
    return penalty, tags


def _recapture_dual_inner_cues(tags: list[str]) -> bool:
    """True if both inner-face FFT periodicity and gradient anisotropy tags fired."""
    return "recapture_fft_periodicity" in tags and "recapture_gradient_aniso" in tags


def _presentation_roi_reliable_for_texture(
    tags: list[str], face_area_ratio: float, quality_penalty: float
) -> bool:
    """True when inner-face texture/recapture may support a spoof verdict (not bad ROI).

    Blur, very small face in frame, tiny face area, or elevated quality penalty block
    uncertain ``clean`` from isolated recapture and force manual review for those
    texture-heavy inputs (texture-without-corroboration uses ``review`` when ROI is ok).

    Args:
        tags: Quality and detector tags from the PAD pipeline.
        face_area_ratio: Face bbox area / image area (0 if unknown).
        quality_penalty: Cumulative quality axis penalty.

    Returns:
        Whether presentation ROI is adequate for texture-driven attack conclusions.
    """
    if any(
        tag in tags
        for tag in ("quality_blur", "quality_small_face", "quality_face_edge_crop")
    ):
        return False
    min_face = _pad_float("presentation_texture_min_face_area_ratio")
    if face_area_ratio > 1e-9 and face_area_ratio < min_face:
        return False
    if quality_penalty >= _pad_float("presentation_texture_max_quality_penalty"):
        return False
    return True


def _presentation_input_insufficient(
    tags: list[str], face_area_ratio: float, quality_penalty: float
) -> bool:
    """Return whether the image lacks enough usable face input for a hard verdict."""
    if any(tag in tags for tag in ("quality_small_face", "quality_face_edge_crop")):
        return True
    min_face = _pad_float("presentation_texture_min_face_area_ratio")
    if face_area_ratio > 1e-9 and face_area_ratio < min_face:
        return True
    if "quality_blur" in tags and any(
        tag in tags
        for tag in ("quality_poor", "quality_low_contrast", "quality_exposure")
    ):
        return True
    if (
        quality_penalty >= _pad_float("quality_degraded_force_review_penalty_min")
        and "quality_poor" in tags
    ):
        return True
    return False


def _mean_clamped(values: list[float]) -> float:
    if not values:
        return 0.0
    return _clamp01(sum(_clamp01(v) for v in values) / float(len(values)))


def _presentation_device_confirmed(tags: list[str], device_score: float) -> bool:
    """Strong on-face COCO device box — ignores weak or multi-class clutter."""
    on_face = [t for t in tags if t.startswith("device_on_face:")]
    score = _clamp01(device_score)
    if score >= _pad_float("decision_device_confirmed_strong_min"):
        return True
    if len(on_face) != 1:
        return False
    return score >= _pad_float("decision_device_confirmed_single_min")


# Short operator-facing copy for the photo feed (see pad_ui_reason tag).
_PAD_UI_REASON_RU: dict[str, str] = {
    "fake_background_display_review": (
        "Модели видят подмену; признаки экрана в фоне (рамки, сертификаты), не у лица. "
        "Нужна проверка."
    ),
    "fake_color_histogram_review": (
        "Модели видят подмену; цвета лица настораживают. Нужна проверка."
    ),
    "fake_default_review_not_clean": (
        "Модели видят риск подмены без явного экрана у лица. Нужна проверка."
    ),
    "fake_plus_face_gated_screen": (
        "Модели и геометрия: у лица признаки экрана или рамки."
    ),
    "fake_extreme_score_suspicious": "Модели почти уверены: кадр похож на подмену.",
    "fake_high_plus_suspicious_device_face": (
        "Высокий риск подмены: устройство подтверждено у лица."
    ),
    "fake_plus_color_histogram_suspicious": (
        "Подмена: модели и цвета лица как на экране."
    ),
    "fake_plus_face_reflection_suspicious": (
        "Обе модели видят подмену; отражение и цвета лица как на экране."
    ),
    "fake_high_confidence_no_geometry_suspicious": (
        "Обе модели уверены в подмене."
    ),
    "presentation_insufficient_input_review": (
        "Лицо или качество не дают уверенного ответа. Нужен новый кадр."
    ),
    "face_reflection_display_suspicious": (
        "Отражение и цвета лица как на экране; подмена вероятна "
        "(не «телефон у лица», а пересъёмка с дисплея)."
    ),
    "color_histogram_display_suspicious": (
        "Цвета лица как на экране, есть подтверждающие признаки."
    ),
    "color_histogram_context_review": (
        "Цвета или блики на лице настораживают; экран у лица не подтверждён. "
        "Нужна проверка."
    ),
    "face_reflection_context_review": (
        "Блики на лице; экран или пересъёмка не подтверждены. Нужна проверка."
    ),
    "strong_face_gated_screen_review": (
        "Признаки экрана у лица; модели не уверены. Нужна проверка."
    ),
    "background_screen_context_review": (
        "В фоне видны признаки экрана или рамки; лицо отдельно. Нужна проверка."
    ),
    "quality_poor_with_face_gated_screen": (
        "Слабый кадр и слабые признаки экрана у лица. Нужна проверка."
    ),
    "ensemble_consensus_review": "Несколько каналов настораживают. Нужна проверка.",
    "ensemble_consensus_suspicious": "Несколько каналов согласованно указывают на подмену.",
    "fake_quality_poor_review": (
        "Модели видят подмену, но кадр слабый — нужна проверка, не автоблок."
    ),
    "fake_quality_limited_review": (
        "Модели видят риск подмены при ограниченном качестве кадра. Нужна проверка."
    ),
}


def _pad_ui_reason_text(branch: str, status: str) -> str:
    if status not in (STATUS_REVIEW, STATUS_SUSPICIOUS):
        return ""
    if branch in _PAD_UI_REASON_RU:
        return _PAD_UI_REASON_RU[branch]
    if status == STATUS_SUSPICIOUS:
        return "Автопроверка: согласованные признаки подмены."
    if status == STATUS_REVIEW:
        return "Автопроверка: сигналы неоднозначны — нужна проверка."
    return ""


def _pad_consensus_jury(inputs: DecisionInputs, tags: list[str]) -> dict[str, Any]:
    """Build an equal-family PAD jury over independent spoof evidence.

    The rule engine below is deliberately conservative and domain-specific. This
    jury gives each evidence family one normalized vote so FasNet/MiniFASNet,
    screen geometry, background context, recapture texture, and face-surface
    artifacts can agree before we escalate. It is used for traceability and for
    safe upgrades from ``clean`` to ``review`` or from ``review`` to
    ``suspicious`` when multiple independent families fire together.
    """
    model_values = [_clamp01(v) for v in inputs.model_scores.values()]
    if model_values:
        if "fasnet_real" in tags and "minifasnet_onnx" in inputs.model_scores:
            neural_model = 0.0
        else:
            neural_model = _mean_clamped(model_values)
    elif (
        "fasnet_fake" in tags
        or "minifasnet_onnx_fake" in tags
        or inputs.deepface_score > 0.0
    ):
        neural_model = _clamp01(inputs.deepface_score)
    else:
        neural_model = 0.0

    face_display = max(
        _mean_clamped([inputs.device_score, inputs.frame_score]),
        min(_clamp01(inputs.device_score), _clamp01(inputs.frame_score)) * 1.12,
    )
    background_display = _mean_clamped(
        [inputs.device_bg_score, inputs.frame_global_score]
    )
    recapture_texture = _clamp01(inputs.recapture_score)
    face_surface = max(_clamp01(inputs.face_reflection_score), _clamp01(inputs.color_hist_score))

    votes = [
        {
            "family": "neural_model",
            "score": neural_model,
            "signals": sorted(inputs.model_scores.keys())
            or [
                tag
                for tag in ("fasnet_fake", "minifasnet_onnx_fake")
                if tag in tags
            ],
        },
        {
            "family": "face_display_geometry",
            "score": _clamp01(face_display),
            "signals": ["device_face", "frame_face"],
        },
        {
            "family": "background_display_context",
            "score": _clamp01(background_display),
            "signals": ["device_bg", "frame_global"],
        },
        {
            "family": "recapture_texture",
            "score": recapture_texture,
            "signals": ["fft", "gradient"],
        },
        {
            "family": "face_surface_artifacts",
            "score": face_surface,
            "signals": ["reflection", "color_histogram"],
        },
    ]
    review_min = _pad_float("ensemble_review_vote_min")
    strong_min = _pad_float("ensemble_strong_vote_min")
    strong = [v["family"] for v in votes if float(v["score"]) >= strong_min]
    review = [v["family"] for v in votes if float(v["score"]) >= review_min]
    active_scores = [
        float(v["score"]) for v in votes if float(v["score"]) >= review_min
    ]
    consensus_score = _mean_clamped(active_scores)
    suspicious_family_min = _pad_int("ensemble_suspicious_family_min")

    decision = STATUS_CLEAN
    if (
        len(strong) >= suspicious_family_min
        and consensus_score >= _pad_float("ensemble_suspicious_score_min")
    ):
        decision = STATUS_SUSPICIOUS
    elif "neural_model" in strong or (
        len(review) >= suspicious_family_min
        and consensus_score >= _pad_float("ensemble_review_score_min")
    ):
        decision = STATUS_REVIEW

    return {
        "decision": decision,
        "score": round(consensus_score, 4),
        "strong_families": strong,
        "review_families": review,
        "votes": [
            {
                "family": str(v["family"]),
                "score": round(float(v["score"]), 4),
                "signals": v["signals"],
            }
            for v in votes
        ],
    }


def _decide(inputs: DecisionInputs) -> PadResult:
    """Single global PAD verdict (pad_v12): jury channels, neural debate, one outcome."""
    from monitoring_app.pad_global_verdict import resolve_global_verdict

    tags = list(dict.fromkeys(inputs.tags))

    if inputs.decode_error:
        return PadResult(
            status=STATUS_ERROR,
            trust_confirmed=None,
            risk_score=0.0,
            tags=["decode_error"],
            deepface_score=inputs.deepface_score,
            device_score=inputs.device_score,
            frame_score=inputs.frame_score,
            quality_penalty=inputs.quality_penalty,
            device_bg_score=inputs.device_bg_score,
            frame_global_score=inputs.frame_global_score,
            recapture_score=inputs.recapture_score,
            face_reflection_score=inputs.face_reflection_score,
            color_hist_score=inputs.color_hist_score,
        )
    if not inputs.has_face or "no_face" in tags:
        return PadResult(
            status=STATUS_ERROR,
            trust_confirmed=None,
            risk_score=0.0,
            tags=["no_face"],
            deepface_score=inputs.deepface_score,
            device_score=inputs.device_score,
            frame_score=inputs.frame_score,
            quality_penalty=inputs.quality_penalty,
            device_bg_score=inputs.device_bg_score,
            frame_global_score=inputs.frame_global_score,
            recapture_score=inputs.recapture_score,
            face_reflection_score=inputs.face_reflection_score,
            color_hist_score=inputs.color_hist_score,
        )

    verdict = resolve_global_verdict(inputs, tags)
    status = verdict.status
    trust = verdict.trust
    branch = verdict.branch
    risk = verdict.risk_score
    jury = verdict.jury
    rec = _clamp01(inputs.recapture_score)
    refl = _clamp01(inputs.face_reflection_score)
    clr = _clamp01(inputs.color_hist_score)
    debate = jury.get("debate") or {}
    neural = float(debate.get("score", inputs.deepface_score))

    ensemble = {
        "decision": jury.get("jury_decision", status),
        "score": jury.get("consensus_score", 0.0),
        "strong_families": jury.get("strong_families", []),
        "review_families": jury.get("review_families", []),
        "votes": jury.get("votes", []),
        "global_spoof_score": jury.get("global_spoof_score", risk),
        "neural_debate": debate,
    }

    tags.append(f"pad_rule:{branch}")
    struct = {
        "schema": PAD_TRACE_SCHEMA,
        "branch": branch,
        "product_outcome": (
            "insufficient_input_review"
            if branch == "presentation_insufficient_input_review"
            else status
        ),
        "deepfake_score": round(neural, 4),
        "device_face": round(inputs.device_score, 4),
        "device_bg_diag": round(inputs.device_bg_score, 4),
        "frame_face": round(inputs.frame_score, 4),
        "frame_global_diag": round(inputs.frame_global_score, 4),
        "recapture": round(rec, 4),
        "face_reflection": round(refl, 4),
        "color_histogram": round(clr, 4),
        "global_verdict": {
            "global_spoof_score": jury.get("global_spoof_score", risk),
            "jury_decision": jury.get("jury_decision"),
            "neural_debate": debate,
        },
        "ensemble_consensus": ensemble,
        "quality_penalty": round(inputs.quality_penalty, 4),
        "face_area_ratio": round(inputs.face_area_ratio, 5),
        "status": status,
    }
    tags.append(
        "pad_evidence:"
        f"df={neural:.3f},dev_f={inputs.device_score:.3f},"
        f"dev_bg={inputs.device_bg_score:.3f},frm_f={inputs.frame_score:.3f},"
        f"frm_gl={inputs.frame_global_score:.3f},rec={rec:.3f},"
        f"refl={refl:.3f},clr={clr:.3f},qp={inputs.quality_penalty:.3f}"
    )
    tags.append(f"pad_struct:{json.dumps(struct, separators=(',', ':'))}")
    tags.append(f"pad_ensemble:{json.dumps(ensemble, separators=(',', ':'))}")
    tags.append(f"pad_global:{json.dumps({'score': jury.get('global_spoof_score', risk), 'debate': debate}, separators=(',', ':'))}")
    ui_reason = _pad_ui_reason_text(branch, status)
    if ui_reason:
        tags.append(f"pad_ui_reason:{ui_reason}")

    return PadResult(
        status=status,
        trust_confirmed=trust,
        risk_score=risk,
        tags=tags,
        deepface_score=inputs.deepface_score,
        device_score=inputs.device_score,
        frame_score=inputs.frame_score,
        quality_penalty=inputs.quality_penalty,
        device_bg_score=inputs.device_bg_score,
        frame_global_score=inputs.frame_global_score,
        recapture_score=rec,
        face_reflection_score=refl,
        color_hist_score=clr,
    )



def check_photo_bgr(img_bgr: np.ndarray, device: Optional[str] = None) -> PadResult:
    """
    Same PAD pipeline as check_photo, for an in-memory BGR image (OpenCV layout).
    """
    started = time.monotonic()
    img_bgr = _downscale_bgr_for_pad(img_bgr)
    requested_device = normalize_device(device)
    face_bbox = _get_primary_face_bbox(img_bgr)
    glasses_mask = _try_glasses_reflection_mask(img_bgr)
    deepface_score, deepface_tags, model_scores = _signal_deepface(
        img_bgr, face_bbox
    )
    device_face, device_bg, device_tags = _signal_device(
        img_bgr, requested_device, face_bbox, glasses_mask=glasses_mask
    )
    frame_face, frame_global, frame_tags = _signal_screen_frame(
        img_bgr, face_bbox, glasses_mask=glasses_mask
    )
    recapture_score, recapture_tags = _signal_recapture(img_bgr, face_bbox)
    reflection_score, reflection_tags = _signal_face_reflection(img_bgr, face_bbox)

    face_area_ratio = 0.0
    if face_bbox is not None:
        fw, fh = face_bbox[2], face_bbox[3]
        ih, iw = img_bgr.shape[:2]
        face_area_ratio = float(max(1, fw * fh)) / float(max(1, ih * iw))
    color_score, color_tags = _signal_color_histogram(
        img_bgr,
        face_bbox,
        face_area_ratio,
    )
    quality_penalty, quality_tags = _signal_quality(img_bgr, face_bbox)

    guard_tags: list[str] = []
    if glasses_mask is not None:
        guard_tags.append("glasses_reflection_guard")

    result = _decide(
        DecisionInputs(
            decode_error=False,
            has_face=face_bbox is not None,
            deepface_score=deepface_score,
            device_score=device_face,
            frame_score=frame_face,
            quality_penalty=quality_penalty,
            tags=(
                deepface_tags
                + device_tags
                + frame_tags
                + recapture_tags
                + reflection_tags
                + color_tags
                + quality_tags
                + guard_tags
            ),
            device_bg_score=device_bg,
            frame_global_score=frame_global,
            recapture_score=recapture_score,
            face_area_ratio=face_area_ratio,
            face_reflection_score=reflection_score,
            color_hist_score=color_score,
            model_scores=model_scores,
        )
    )
    result.elapsed_ms = (time.monotonic() - started) * 1000.0
    return result


def check_photo(image_path: str | Path, device: Optional[str] = None) -> PadResult:
    started = time.monotonic()
    img_bgr = _CV2_IMREAD(str(image_path))
    if img_bgr is None:
        result = _decide(
            DecisionInputs(
                decode_error=True,
                has_face=False,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.0,
                tags=["decode_error"],
            )
        )
        result.elapsed_ms = (time.monotonic() - started) * 1000.0
        return result

    return check_photo_bgr(img_bgr, device=device)
