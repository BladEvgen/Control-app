from __future__ import annotations

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


logger = logging.getLogger(__name__)

PAD_MODEL_VERSION = "pad_v2"

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

_CV2_COLOR_BGR2RGB = int(_cv2_get_attr("COLOR_BGR2RGB"))
_CV2_COLOR_BGR2GRAY = int(_cv2_get_attr("COLOR_BGR2GRAY"))
_CV2_MORPH_RECT = int(_cv2_get_attr("MORPH_RECT"))
_CV2_RETR_EXTERNAL = int(_cv2_get_attr("RETR_EXTERNAL"))
_CV2_CHAIN_APPROX_SIMPLE = int(_cv2_get_attr("CHAIN_APPROX_SIMPLE"))
_CV2_CV_64F = int(_cv2_get_attr("CV_64F"))

_PAD_DEFAULT_NUMBERS: dict[str, float | int] = {
    "device_min_conf": 0.20,
    "device_min_area_ratio": 0.02,
    "device_ratio_ref": 0.25,
    "device_score_conf_weight": 0.60,
    "device_score_ratio_weight": 0.40,
    "frame_canny_low": 60,
    "frame_canny_high": 160,
    "frame_gaussian_kernel": 5,
    "frame_dilate_kernel": 3,
    "frame_min_area_ratio": 0.12,
    "frame_poly_epsilon": 0.02,
    "frame_min_solidity": 0.80,
    "frame_ratio_ref": 0.55,
    "frame_face_bonus": 0.15,
    "frame_border_bonus": 0.08,
    "frame_border_margin_px": 8,
    "frame_tag_threshold": 0.35,
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
    "risk_weight_deepface": 0.50,
    "risk_weight_device": 0.30,
    "risk_weight_frame": 0.20,
    "risk_quality_discount_max": 0.18,
    "risk_quality_discount_scale": 0.25,
    "decision_device_present_min": 0.25,
    "decision_frame_present_min": 0.40,
    "decision_strong_device_min": 0.35,
    "decision_strong_frame_min": 0.30,
    "decision_very_strong_device_min": 0.55,
    "decision_quality_poor_min": 0.45,
    "decision_deepfake_review_min": 0.65,
    "decision_deepfake_device_min": 0.90,
    "decision_deepfake_very_high": 0.96,
    "decision_suspicious_device_min": 0.25,
    "decision_suspicious_frame_min": 0.45,
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
    decode_error: bool
    has_face: bool
    deepface_score: float
    device_score: float
    frame_score: float
    quality_penalty: float
    tags: list[str]


def normalize_device(device: Optional[str] = None) -> str:
    configured = (device or getattr(settings, "PHOTO_PAD_DEVICE", DEVICE_AUTO) or DEVICE_AUTO)
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
            (torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")),
            (DEVICE_CUDA if torch.cuda.is_available() else DEVICE_CPU),
        )
    if preferred_device == DEVICE_CPU:
        return torch.device("cpu"), DEVICE_CPU
    if torch.cuda.is_available():
        return torch.device("cuda"), DEVICE_CUDA
    return torch.device("cpu"), DEVICE_CPU


def _get_fasnet():
    if "fasnet" in _runtime_cache:
        return _runtime_cache["fasnet"]
    try:
        from deepface.models.spoofing.FasNet import Fasnet

        _runtime_cache["fasnet"] = Fasnet()
    except Exception as exc:
        logger.warning("FasNet is unavailable: %s", exc)
        _runtime_cache["fasnet"] = None
    return _runtime_cache["fasnet"]


def _get_primary_face_bbox(img_bgr: np.ndarray) -> Optional[tuple[int, int, int, int]]:
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


def _signal_deepface(img_bgr: np.ndarray, face_bbox: Optional[tuple[int, int, int, int]]) -> tuple[float, list[str]]:
    if face_bbox is None:
        return 0.0, ["no_face"]

    fasnet = _get_fasnet()
    if fasnet is None:
        return 0.0, ["fasnet_unavailable"]

    try:
        is_real, raw_score = fasnet.analyze(img=img_bgr, facial_area=face_bbox)
        score = max(0.0, min(1.0, float(raw_score)))
        if is_real is False:
            return score, ["fasnet_fake"]
        return 0.0, []
    except Exception as exc:
        logger.warning("FasNet inference failed: %s", exc)
        return 0.0, ["deepface_error"]


def _get_device_detector(preferred_device: str) -> tuple[Optional[Any], Optional[Any], str]:
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


def _signal_device(img_bgr: np.ndarray, preferred_device: str) -> tuple[float, list[str]]:
    model, torch_module, _resolved_device = _get_device_detector(preferred_device)
    if model is None or torch_module is None:
        return 0.0, []

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
        best_score = 0.0

        for label, confidence, box in zip(labels, scores, boxes):
            if label not in _COCO_DEVICE_CLASSES:
                continue
            if confidence < _pad_float("device_min_conf"):
                continue
            x1, y1, x2, y2 = box
            area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
            ratio = area / frame_area
            if ratio < _pad_float("device_min_area_ratio"):
                continue
            device_name = _COCO_DEVICE_CLASSES[label]
            tags.append(f"device_present:{device_name}")
            ratio_factor = min(1.0, ratio / _pad_float("device_ratio_ref"))
            confidence_factor = min(1.0, confidence)
            candidate = min(
                1.0,
                _pad_float("device_score_conf_weight") * confidence_factor
                + _pad_float("device_score_ratio_weight") * ratio_factor,
            )
            best_score = max(best_score, candidate)

        return best_score, sorted(set(tags))
    except Exception as exc:
        logger.warning("Device detector inference failed: %s", exc)
        return 0.0, []


def _signal_screen_frame(
    img_bgr: np.ndarray, face_bbox: Optional[tuple[int, int, int, int]]
) -> tuple[float, list[str]]:
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
    edges = _CV2_CANNY(
        _CV2_GAUSSIAN_BLUR(gray, (gaussian_kernel, gaussian_kernel), 0),
        _pad_int("frame_canny_low"),
        _pad_int("frame_canny_high"),
    )
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

    best_score = 0.0
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

        candidate = min(1.0, area_ratio / _pad_float("frame_ratio_ref"))

        if face_center is not None:
            cx, cy = face_center
            if x <= cx <= (x + bw) and y <= cy <= (y + bh):
                candidate = min(1.0, candidate + _pad_float("frame_face_bonus"))

        border_margin = _pad_int("frame_border_margin_px")
        near_borders = (
            (x <= border_margin)
            or (y <= border_margin)
            or ((x + bw) >= w - border_margin)
            or ((y + bh) >= h - border_margin)
        )
        if near_borders:
            candidate = min(1.0, candidate + _pad_float("frame_border_bonus"))

        best_score = max(best_score, candidate)

    if best_score >= _pad_float("frame_tag_threshold"):
        return best_score, ["screen_frame"]
    return best_score, []


def _signal_quality(
    img_bgr: np.ndarray, face_bbox: Optional[tuple[int, int, int, int]]
) -> tuple[float, list[str]]:
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
    if (
        brightness < _pad_float("quality_brightness_min")
        or brightness > _pad_float("quality_brightness_max")
    ):
        penalty += _pad_float("quality_penalty_exposure")
        tags.append("quality_exposure")
    if contrast < _pad_float("quality_contrast_min"):
        penalty += _pad_float("quality_penalty_contrast")
        tags.append("quality_low_contrast")
    if face_bbox is not None and face_ratio < _pad_float("quality_face_ratio_min"):
        penalty += _pad_float("quality_penalty_small_face")
        tags.append("quality_small_face")

    penalty = min(1.0, penalty)
    if penalty >= _pad_float("quality_poor_threshold"):
        tags.append("quality_poor")
    return penalty, tags


def _decide(inputs: DecisionInputs) -> PadResult:
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
        )

    deepfake = "fasnet_fake" in tags
    has_device = inputs.device_score >= _pad_float("decision_device_present_min")
    has_frame = inputs.frame_score >= _pad_float("decision_frame_present_min")
    strong_screen = (
        inputs.device_score >= _pad_float("decision_strong_device_min")
        and inputs.frame_score >= _pad_float("decision_strong_frame_min")
    ) or (
        inputs.device_score >= _pad_float("decision_very_strong_device_min")
    )
    quality_poor = (
        inputs.quality_penalty >= _pad_float("decision_quality_poor_min")
        or "quality_poor" in tags
    )

    risk = (
        _pad_float("risk_weight_deepface") * inputs.deepface_score
        + _pad_float("risk_weight_device") * inputs.device_score
        + _pad_float("risk_weight_frame") * inputs.frame_score
    )
    risk -= min(
        _pad_float("risk_quality_discount_max"),
        inputs.quality_penalty * _pad_float("risk_quality_discount_scale"),
    )
    risk = max(0.0, min(1.0, risk))

    if deepfake and (strong_screen or (has_device and has_frame)):
        status = STATUS_SUSPICIOUS
        trust = False
    elif (
        deepfake
        and inputs.deepface_score >= _pad_float("decision_deepfake_device_min")
        and inputs.device_score >= _pad_float("decision_suspicious_device_min")
        and not quality_poor
    ):
        status = STATUS_SUSPICIOUS
        trust = False
    elif (
        deepfake
        and inputs.deepface_score >= _pad_float("decision_deepfake_very_high")
        and (has_device or has_frame)
        and not quality_poor
    ):
        status = STATUS_SUSPICIOUS
        trust = False
    elif (
        strong_screen
        and inputs.device_score >= _pad_float("decision_suspicious_device_min")
        and inputs.frame_score >= _pad_float("decision_suspicious_frame_min")
    ):
        status = STATUS_SUSPICIOUS
        trust = False
    elif deepfake:
        if (
            inputs.deepface_score < _pad_float("decision_deepfake_review_min")
            and not has_device
            and not has_frame
            and not quality_poor
        ):
            status = STATUS_CLEAN
            trust = True
        else:
            status = STATUS_REVIEW
            trust = None
    elif strong_screen and not quality_poor:
        status = STATUS_REVIEW
        trust = None
    else:
        status = STATUS_CLEAN
        trust = True

    return PadResult(
        status=status,
        trust_confirmed=trust,
        risk_score=risk,
        tags=tags,
        deepface_score=inputs.deepface_score,
        device_score=inputs.device_score,
        frame_score=inputs.frame_score,
        quality_penalty=inputs.quality_penalty,
    )


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

    requested_device = normalize_device(device)
    face_bbox = _get_primary_face_bbox(img_bgr)
    deepface_score, deepface_tags = _signal_deepface(img_bgr, face_bbox)
    device_score, device_tags = _signal_device(img_bgr, requested_device)
    frame_score, frame_tags = _signal_screen_frame(img_bgr, face_bbox)
    quality_penalty, quality_tags = _signal_quality(img_bgr, face_bbox)

    result = _decide(
        DecisionInputs(
            decode_error=False,
            has_face=face_bbox is not None,
            deepface_score=deepface_score,
            device_score=device_score,
            frame_score=frame_score,
            quality_penalty=quality_penalty,
            tags=deepface_tags + device_tags + frame_tags + quality_tags,
        )
    )
    result.elapsed_ms = (time.monotonic() - started) * 1000.0
    return result
