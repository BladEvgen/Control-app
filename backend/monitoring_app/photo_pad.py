from __future__ import annotations

import json
import logging
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

PAD_MODEL_VERSION = "pad_v7"

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

_CV2_COLOR_BGR2RGB = int(_cv2_get_attr("COLOR_BGR2RGB"))
_CV2_COLOR_BGR2GRAY = int(_cv2_get_attr("COLOR_BGR2GRAY"))
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


def _get_primary_face_bbox(img_bgr: np.ndarray) -> Optional[tuple[int, int, int, int]]:
    """Return the largest ArcFace-detected face as ``(x, y, w, h)``.

    Args:
        img_bgr: BGR image.

    Returns:
        Bounding box or None if detection fails.
    """
    try:
        ml.load_arcface_model()
        arcface_instance = ml.arcface_model_holder.instance
        if arcface_instance is None:
            return None
        faces = arcface_instance.get(img_bgr)
        if not faces:
            return None
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
        return None


def _signal_deepface(
    img_bgr: np.ndarray, face_bbox: Optional[tuple[int, int, int, int]]
) -> tuple[float, list[str]]:
    """Run FasNet anti-spoof on the primary face (spoof score + tags)."""
    if face_bbox is None:
        return 0.0, ["no_face"]

    fasnet = _get_fasnet()
    if fasnet is None:
        return 0.0, ["fasnet_unavailable", "pad_spoof_model_missing"]

    try:
        is_real, raw_score = fasnet.analyze(img=img_bgr, facial_area=face_bbox)
        score = max(0.0, min(1.0, float(raw_score)))
        if is_real is False:
            return score, ["fasnet_fake"]
        return 0.0, []
    except Exception as exc:
        logger.warning("FasNet inference failed: %s", exc)
        return 0.0, ["deepface_error"]


def _get_device_detector(
    preferred_device: str,
) -> tuple[Optional[Any], Optional[Any], str]:
    cache_key = f"detector:{preferred_device}"
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


def _decide(inputs: DecisionInputs) -> PadResult:
    """Fuse PAD channels with corroboration rules, shielding, and structured trace.

    FasNet and face geometry drive hard ``suspicious``. Inner-face FFT/anisotropy
    and recapture without corroboration yield ``review`` when the ROI is reliable,
    or insufficient-input ``review`` when it is not; they do not auto-``suspicious``
    calm-channel live photos.

    Args:
        inputs: Per-channel scores and tags from the PAD pipeline.

    Returns:
        PadResult including human-readable tags and ``pad_struct`` JSON.
    """
    tags = list(dict.fromkeys(inputs.tags))
    trace: list[str] = []

    def _append_trace(rule: str) -> None:
        trace.append(f"pad_rule:{rule}")

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
        )

    deepfake = "fasnet_fake" in tags
    spoof_model_uncertain = (
        "fasnet_unavailable" in tags
        or "deepface_error" in tags
        or "pad_spoof_model_missing" in tags
    )
    rec = float(inputs.recapture_score)
    rec_mid = _pad_float("recapture_mid")
    rec_strong = _pad_float("recapture_strong")
    rec_review_min = _pad_float("decision_recapture_review_min")
    rec_corr_min = _pad_float("decision_recapture_corroboration_min")

    has_device = inputs.device_score >= _pad_float("decision_device_present_min")
    has_frame = inputs.frame_score >= _pad_float("decision_frame_present_min")
    mid_device = inputs.device_score >= _pad_float("decision_mid_device_min")
    mid_frame = inputs.frame_score >= _pad_float("decision_mid_frame_min")
    strong_screen = inputs.device_score >= _pad_float(
        "decision_strong_device_min"
    ) and inputs.frame_score >= _pad_float("decision_strong_frame_min")
    quality_poor = (
        inputs.quality_penalty >= _pad_float("decision_quality_poor_min")
        or "quality_poor" in tags
    )
    insufficient_input = _presentation_input_insufficient(
        tags, inputs.face_area_ratio, inputs.quality_penalty
    )
    q_rev_dev = _pad_float("decision_quality_device_review_min")
    q_rev_frm = _pad_float("decision_quality_frame_review_min")
    q_rev_sum = _pad_float("decision_quality_combined_review_sum_min")
    quality_review_signal = (
        inputs.device_score >= q_rev_dev and inputs.frame_score >= q_rev_frm
    ) or (inputs.device_score + inputs.frame_score >= q_rev_sum)
    background_screen_context = inputs.device_bg_score >= max(
        _pad_float("decision_strong_device_min"), 0.52
    ) or inputs.frame_global_score >= max(_pad_float("decision_strong_frame_min"), 0.42)
    credible_display_context = background_screen_context or (
        "screen_bezel_context" in tags
        and inputs.frame_global_score >= _pad_float("decision_weak_frame_min")
    )
    strong_display_context = background_screen_context or (
        "screen_bezel_context" in tags
        and inputs.frame_global_score >= _pad_float("decision_frame_present_min")
    )
    high_fake_without_geometry = inputs.deepface_score >= _pad_float(
        "decision_deepfake_device_min"
    ) and inputs.quality_penalty < _pad_float(
        "quality_degraded_force_review_penalty_min"
    )
    reflection_guard_fake = (
        "glasses_reflection_guard" in tags
        and not has_device
        and not has_frame
        and rec < rec_review_min
    )

    shield = (
        not deepfake
        and not quality_poor
        and inputs.quality_penalty < _pad_float("shield_max_quality_penalty")
        and inputs.device_score <= _pad_float("shield_max_device_face")
        and inputs.frame_score <= _pad_float("shield_max_frame_face")
        and rec <= _pad_float("shield_max_recapture")
    )
    ch_rec_corr = rec >= rec_corr_min

    risk = (
        _pad_float("risk_weight_deepface") * inputs.deepface_score
        + _pad_float("risk_weight_device") * inputs.device_score
        + _pad_float("risk_weight_frame") * inputs.frame_score
        + _pad_float("risk_weight_recapture") * rec
    )
    risk = max(0.0, min(1.0, risk))

    status = STATUS_CLEAN
    trust: Optional[bool] = True
    branch = "default_clean"

    susp_dev = inputs.device_score >= _pad_float("decision_suspicious_device_min")
    susp_frm = inputs.frame_score >= _pad_float("decision_suspicious_frame_min")
    dual_mid_geometry = mid_device and mid_frame
    dual_susp_geometry = susp_dev and susp_frm

    if deepfake:
        if strong_screen or (has_device and has_frame):
            status = STATUS_SUSPICIOUS
            trust = False
            branch = "fake_plus_face_gated_screen"
            _append_trace(branch)
        elif inputs.deepface_score >= _pad_float("decision_deepfake_very_high") and (
            dual_susp_geometry or rec >= rec_mid
        ):
            status = STATUS_SUSPICIOUS
            trust = False
            branch = "fake_extreme_score_suspicious"
            _append_trace(branch)
        elif (
            inputs.deepface_score >= _pad_float("decision_deepfake_device_min")
            and susp_dev
            and has_frame
        ):
            status = STATUS_SUSPICIOUS
            trust = False
            branch = "fake_high_plus_suspicious_device_face"
            _append_trace(branch)
        elif (
            inputs.deepface_score >= _pad_float("decision_deepfake_mid_suspicious_min")
            and dual_mid_geometry
        ):
            status = STATUS_SUSPICIOUS
            trust = False
            branch = "fake_mid_plus_dual_mid_geometry"
            _append_trace(branch)
        elif (
            rec >= rec_strong
            and inputs.deepface_score
            >= _pad_float("decision_deepfake_mid_suspicious_min")
            and ch_rec_corr
            and (dual_mid_geometry or dual_susp_geometry or (has_device and has_frame))
        ):
            status = STATUS_SUSPICIOUS
            trust = False
            branch = "fake_plus_strong_recapture_corroborated"
            _append_trace(branch)
        elif (
            inputs.deepface_score >= _pad_float("decision_deepfake_mid_suspicious_min")
            and strong_display_context
        ):
            status = STATUS_SUSPICIOUS
            trust = False
            branch = "fake_mid_plus_background_display_suspicious"
            _append_trace(branch)
        elif high_fake_without_geometry:
            status = STATUS_SUSPICIOUS
            trust = False
            branch = "fake_high_confidence_no_geometry_suspicious"
            _append_trace(branch)
        elif (
            inputs.deepface_score >= _pad_float("decision_deepfake_review_min")
            and credible_display_context
        ):
            status = STATUS_REVIEW
            trust = None
            branch = "fake_background_display_review"
            _append_trace(branch)
        elif (
            "quality_blur" in tags
            or "quality_low_contrast" in tags
            or "quality_exposure" in tags
        ):
            status = STATUS_REVIEW
            trust = None
            branch = "fake_quality_limited_review"
            _append_trace(branch)
        elif insufficient_input:
            status = STATUS_REVIEW
            trust = None
            branch = "fake_quality_limited_review"
            _append_trace(branch)
        elif quality_poor:
            status = STATUS_REVIEW
            trust = None
            branch = "fake_quality_poor_review"
            _append_trace(branch)
        elif reflection_guard_fake:
            status = STATUS_REVIEW
            trust = None
            branch = "fake_reflection_guard_review"
            _append_trace(branch)
        elif (
            inputs.deepface_score < _pad_float("decision_deepfake_review_min")
            and not mid_device
            and not mid_frame
        ):
            status = STATUS_CLEAN
            trust = True
            branch = "fake_low_confidence_no_geometry_clean"
            _append_trace(branch)
        else:
            status = STATUS_REVIEW
            trust = None
            branch = "fake_default_review_not_clean"
            _append_trace(branch)
    elif (
        strong_screen
        and dual_susp_geometry
        and not quality_poor
        and not insufficient_input
        and inputs.face_area_ratio >= _pad_float("no_fake_susp_min_face_area_ratio")
    ):
        status = STATUS_SUSPICIOUS
        trust = False
        branch = "no_fake_dual_suspicious_geometry"
        _append_trace(branch)
    elif strong_screen and dual_susp_geometry and not quality_poor:
        status = STATUS_REVIEW
        trust = None
        branch = (
            "presentation_insufficient_input_review"
            if insufficient_input
            else "no_fake_dual_geom_small_face_review"
        )
        _append_trace(branch)
    elif (
        strong_screen
        and not quality_poor
        and not insufficient_input
        and dual_mid_geometry
        and inputs.face_area_ratio >= _pad_float("no_fake_susp_min_face_area_ratio")
    ):
        status = STATUS_SUSPICIOUS
        trust = False
        branch = "strong_screen_dual_mid_geometry_suspicious"
        _append_trace(branch)
    elif strong_screen and not quality_poor and (has_device or has_frame):
        status = STATUS_REVIEW
        trust = None
        branch = (
            "presentation_insufficient_input_review"
            if insufficient_input
            else "strong_face_gated_screen_review"
        )
        _append_trace(branch)
    elif (
        rec >= rec_strong
        and ch_rec_corr
        and dual_susp_geometry
        and not quality_poor
        and not insufficient_input
        and inputs.face_area_ratio >= _pad_float("no_fake_susp_min_face_area_ratio")
    ):
        status = STATUS_SUSPICIOUS
        trust = False
        branch = "no_fake_recapture_strong_corroborated_dual_geometry"
        _append_trace(branch)
    elif rec >= rec_strong and ch_rec_corr and dual_susp_geometry and not quality_poor:
        status = STATUS_REVIEW
        trust = None
        branch = "no_fake_recapture_strong_dual_geometry_small_face_review"
        _append_trace(branch)
    elif rec >= rec_strong:
        roi_tex = _presentation_roi_reliable_for_texture(
            tags, inputs.face_area_ratio, inputs.quality_penalty
        )
        isolated_rec = not has_device and not has_frame and not quality_poor
        dual_tex = _recapture_dual_inner_cues(tags)
        qp_iso = inputs.quality_penalty
        moire_rec = _pad_float("recapture_isolated_moire_forgive_min_rec")
        moire_qp = _pad_float("recapture_isolated_moire_max_quality_penalty")
        ext_single = _pad_float("recapture_isolated_extreme_single_channel_min")
        if isolated_rec:
            if dual_tex and rec >= moire_rec and qp_iso < moire_qp:
                if roi_tex:
                    status = STATUS_CLEAN
                    trust = None
                    branch = "recapture_isolated_extreme_moire_live_uncertain_clean"
                else:
                    status = STATUS_REVIEW
                    trust = None
                    branch = "presentation_insufficient_input_review"
                _append_trace(branch)
            elif dual_tex:
                if roi_tex:
                    status = STATUS_REVIEW
                    trust = None
                    branch = "recapture_isolated_dual_texture_ambiguous_review"
                else:
                    status = STATUS_REVIEW
                    trust = None
                    branch = "presentation_insufficient_input_review"
                _append_trace(branch)
            elif rec >= ext_single and not dual_tex:
                if roi_tex:
                    status = STATUS_CLEAN
                    trust = None
                    branch = "recapture_isolated_extreme_single_channel_uncertain_clean"
                else:
                    status = STATUS_REVIEW
                    trust = None
                    branch = "presentation_insufficient_input_review"
                _append_trace(branch)
            else:
                if roi_tex:
                    status = STATUS_CLEAN
                    trust = None
                    if dual_tex:
                        branch = (
                            "recapture_isolated_dual_texture_low_rec_uncertain_clean"
                        )
                    else:
                        branch = "recapture_isolated_single_cue_texture_clean"
                else:
                    status = STATUS_REVIEW
                    trust = None
                    branch = "presentation_insufficient_input_review"
                _append_trace(branch)
        else:
            if quality_poor:
                status = STATUS_REVIEW
                trust = None
                branch = (
                    "presentation_insufficient_input_review"
                    if insufficient_input
                    else "recapture_strong_quality_context_review"
                )
                _append_trace(branch)
            elif dual_susp_geometry:
                if roi_tex:
                    status = STATUS_SUSPICIOUS
                    trust = False
                    branch = "recapture_strong_face_geometry_suspicious"
                else:
                    status = STATUS_REVIEW
                    trust = None
                    branch = "presentation_insufficient_input_review"
                _append_trace(branch)
            elif roi_tex:
                status = STATUS_REVIEW
                trust = None
                branch = "recapture_strong_loose_context_ambiguous_review"
                _append_trace(branch)
            else:
                status = STATUS_REVIEW
                trust = None
                branch = "presentation_insufficient_input_review"
                _append_trace(branch)
    elif rec >= rec_mid and (has_device or has_frame):
        if dual_susp_geometry:
            status = STATUS_SUSPICIOUS
            trust = False
            branch = "recapture_mid_with_suspicious_context_suspicious"
            _append_trace(branch)
        elif insufficient_input:
            status = STATUS_REVIEW
            trust = None
            branch = "presentation_insufficient_input_review"
            _append_trace(branch)
        else:
            status = STATUS_CLEAN
            trust = None
            branch = "recapture_mid_weak_geometry_clean"
            _append_trace(branch)
    elif rec >= rec_review_min and spoof_model_uncertain:
        if rec < rec_mid:
            status = STATUS_CLEAN
            trust = None
            branch = "spoof_model_uncertain_low_recapture_clean"
            _append_trace(branch)
        elif rec >= rec_mid and (ch_rec_corr or _recapture_dual_inner_cues(tags)):
            status = STATUS_REVIEW
            trust = None
            branch = "spoof_uncertain_texture_ambiguous_review"
            _append_trace(branch)
        else:
            status = STATUS_CLEAN
            trust = None
            branch = "spoof_model_uncertain_recapture_uncertain_clean"
            _append_trace(branch)
    elif credible_display_context and not has_device and not has_frame:
        status = STATUS_REVIEW
        trust = None
        branch = "background_screen_context_review"
        _append_trace(branch)
    elif quality_poor and quality_review_signal:
        status = STATUS_REVIEW
        trust = None
        branch = (
            "presentation_insufficient_input_review"
            if insufficient_input
            else "quality_poor_with_face_gated_screen"
        )
        _append_trace(branch)
    elif quality_poor and (
        has_device
        or has_frame
        or rec >= rec_review_min
        or inputs.quality_penalty
        >= _pad_float("quality_degraded_force_review_penalty_min")
    ):
        status = STATUS_REVIEW
        trust = None
        branch = (
            "presentation_insufficient_input_review"
            if insufficient_input
            else "image_quality_degraded_review"
        )
        _append_trace(branch)
    elif insufficient_input:
        status = STATUS_REVIEW
        trust = None
        branch = "presentation_insufficient_input_review"
        _append_trace(branch)
    elif (
        inputs.quality_penalty > 0.0
        and any(
            tag in tags
            for tag in ("quality_blur", "quality_low_contrast", "quality_exposure")
        )
        and not quality_poor
        and not deepfake
        and not has_device
        and not has_frame
        and rec < rec_review_min
        and not credible_display_context
    ):
        status = STATUS_CLEAN
        trust = None
        branch = "image_quality_uncertain_clean"
        _append_trace(branch)
    elif quality_poor:
        status = STATUS_CLEAN
        trust = None
        branch = "image_quality_uncertain_clean"
        _append_trace(branch)
    elif spoof_model_uncertain and not quality_poor:
        weak_dev = _pad_float("decision_weak_device_min")
        weak_frm = _pad_float("decision_weak_frame_min")
        weak_sum = _pad_float("decision_weak_combined_sum_min")
        if (inputs.device_score >= weak_dev or inputs.frame_score >= weak_frm) and (
            inputs.device_score + inputs.frame_score >= weak_sum
        ):
            status = STATUS_REVIEW
            trust = None
            branch = "spoof_model_uncertain_weak_face_geometry"
            _append_trace(branch)
        else:
            status = STATUS_CLEAN
            trust = True
            branch = "spoof_model_uncertain_clean_fallback"
            _append_trace(branch)
    else:
        weak_dev = _pad_float("decision_weak_device_min")
        weak_frm = _pad_float("decision_weak_frame_min")
        weak_sum = _pad_float("decision_weak_combined_sum_min")
        weak_hit = (
            not quality_poor
            and (inputs.device_score >= weak_dev or inputs.frame_score >= weak_frm)
            and (inputs.device_score + inputs.frame_score >= weak_sum)
        )
        if (
            not deepfake
            and inputs.device_score >= weak_dev
            and not has_frame
            and rec < rec_mid
            and not quality_poor
            and not insufficient_input
        ):
            status = STATUS_CLEAN
            trust = None
            branch = "device_only_context_uncertain_clean"
            _append_trace(branch)
        elif weak_hit and not shield:
            status = STATUS_REVIEW
            trust = None
            branch = "weak_face_gated_combined_review"
            _append_trace(branch)
        elif weak_hit and shield:
            status = STATUS_CLEAN
            trust = True
            branch = "shield_weak_geometry_clean"
            _append_trace(branch)
        else:
            status = STATUS_CLEAN
            trust = True
            branch = "default_clean"
            _append_trace(branch)

    struct = {
        "schema": PAD_TRACE_SCHEMA,
        "branch": branch,
        "product_outcome": (
            "insufficient_input_review"
            if branch == "presentation_insufficient_input_review"
            else status
        ),
        "deepfake_score": round(inputs.deepface_score, 4),
        "device_face": round(inputs.device_score, 4),
        "device_bg_diag": round(inputs.device_bg_score, 4),
        "frame_face": round(inputs.frame_score, 4),
        "frame_global_diag": round(inputs.frame_global_score, 4),
        "recapture": round(rec, 4),
        "quality_penalty": round(inputs.quality_penalty, 4),
        "face_area_ratio": round(inputs.face_area_ratio, 5),
        "shield_normal_live": shield,
        "corroboration": {
            "fasnet_fake": deepfake,
            "mid_device": mid_device,
            "mid_frame": mid_frame,
            "recapture_corr": ch_rec_corr,
        },
        "status": status,
    }
    tags.extend(trace)
    tags.append(
        "pad_evidence:"
        f"df={inputs.deepface_score:.3f},dev_f={inputs.device_score:.3f},"
        f"dev_bg={inputs.device_bg_score:.3f},frm_f={inputs.frame_score:.3f},"
        f"frm_gl={inputs.frame_global_score:.3f},rec={rec:.3f},qp={inputs.quality_penalty:.3f}"
    )
    tags.append(f"pad_struct:{json.dumps(struct, separators=(',', ':'))}")

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
    deepface_score, deepface_tags = _signal_deepface(img_bgr, face_bbox)
    device_face, device_bg, device_tags = _signal_device(
        img_bgr, requested_device, face_bbox, glasses_mask=glasses_mask
    )
    frame_face, frame_global, frame_tags = _signal_screen_frame(
        img_bgr, face_bbox, glasses_mask=glasses_mask
    )
    recapture_score, recapture_tags = _signal_recapture(img_bgr, face_bbox)
    quality_penalty, quality_tags = _signal_quality(img_bgr, face_bbox)

    face_area_ratio = 0.0
    if face_bbox is not None:
        fw, fh = face_bbox[2], face_bbox[3]
        ih, iw = img_bgr.shape[:2]
        face_area_ratio = float(max(1, fw * fh)) / float(max(1, ih * iw))

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
                + quality_tags
                + guard_tags
            ),
            device_bg_score=device_bg,
            frame_global_score=frame_global,
            recapture_score=recapture_score,
            face_area_ratio=face_area_ratio,
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
