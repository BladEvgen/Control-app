"""
BiSeNet face parsing (CelebAMask-HQ, 19 classes) for RGB photos — eyeglasses mask / detection.

Uses yakhyo/face-parsing ONNX (ResNet18 backbone): same preprocessing as upstream onnx_inference.py.
Class index 6 == eye_g (eyeglasses); see yakhyo utils/common.py ATTRIBUTES.
"""
from __future__ import annotations

import logging
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np
from django.conf import settings

logger = logging.getLogger(__name__)

_SESSION_LOCK = threading.Lock()


@dataclass
class _FaceParsingRuntime:
    """Модульное состояние без global в функциях (pylint W0603)."""

    engine: Optional["FaceParsingEngine"] = None
    load_failed: bool = False
    missing_model_logged: bool = False

    def reset(self) -> None:
        self.engine = None
        self.load_failed = False
        self.missing_model_logged = False


_RT = _FaceParsingRuntime()

# 0=background; 1=skin … 6=eye_g (eyeglasses) in yakhyo face-parsing label order
EYEGLASSES_CLASS_ID = 6

DEFAULT_DOWNLOAD_URL = (
    "https://github.com/yakhyo/face-parsing/releases/download/weights/resnet18.onnx"
)


class FaceParsingEngine:
    """ONNXRuntime session; input BGR uint8, output per-pixel class id uint8 (H,W)."""

    def __init__(self, model_path: Path) -> None:
        import onnxruntime as ort

        try:
            import torch

            cuda_ok = bool(torch.cuda.is_available())
        except Exception:
            cuda_ok = False
        providers = (
            ["CUDAExecutionProvider", "CPUExecutionProvider"]
            if cuda_ok
            else ["CPUExecutionProvider"]
        )
        self._session = ort.InferenceSession(
            str(model_path), providers=providers
        )
        self.input_size = (512, 512)
        self._mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        self._std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        self._input_name = self._session.get_inputs()[0].name
        self._output_names = [o.name for o in self._session.get_outputs()]

    def predict_mask_bgr(self, image_bgr: np.ndarray) -> np.ndarray:
        if image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
            raise ValueError("image_bgr must be HxWx3 BGR")
        h, w = image_bgr.shape[:2]
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, self.input_size, interpolation=cv2.INTER_LINEAR)
        x = resized.astype(np.float32) / 255.0
        x = (x - self._mean) / self._std
        x = np.transpose(x, (2, 0, 1))
        x = np.expand_dims(x, axis=0).astype(np.float32)
        out = self._session.run(self._output_names, {self._input_name: x})[0]
        logits = np.asarray(out)
        if logits.ndim == 4:
            mask = np.argmax(logits.squeeze(0), axis=0).astype(np.uint8)
        elif logits.ndim == 3:
            mask = np.argmax(logits, axis=0).astype(np.uint8)
        else:
            raise RuntimeError(f"Unexpected parsing output shape {logits.shape}")
        return cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)

    def predict_mask_rgb(self, image_rgb: np.ndarray) -> np.ndarray:
        bgr = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
        return self.predict_mask_bgr(bgr)

    @staticmethod
    def eyeglasses_area_frac(mask: np.ndarray) -> float:
        return float(np.mean(mask == EYEGLASSES_CLASS_ID))

    def eyeglasses_inpaint_mask_u8(
        self,
        rgb: np.ndarray,
        dilate: int,
    ) -> Optional[np.ndarray]:
        """Binary uint8 mask 255 on eyeglasses class; None if too small."""
        mask_labels = self.predict_mask_rgb(rgb)
        g = ((mask_labels == EYEGLASSES_CLASS_ID).astype(np.uint8)) * 255
        if int(np.count_nonzero(g)) < 10:
            return None
        k = max(int(dilate), 3)
        if k % 2 == 0:
            k += 1
        g = cv2.dilate(g, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
        return g


def model_path_resolved() -> Path:
    raw = getattr(settings, "FACE_PARSING_MODEL_PATH", None)
    if raw:
        return Path(str(raw)).expanduser().resolve()
    root = getattr(settings, "GENERAL_MODELS_ROOT", None)
    base = Path(root).expanduser().resolve() if root else Path(".")
    return base / "face_parsing_resnet18.onnx"


def _ensure_model_file(path: Path) -> bool:
    if path.is_file():
        return True
    if not bool(getattr(settings, "FACE_PARSING_AUTO_DOWNLOAD", False)):
        if not _RT.missing_model_logged:
            logger.warning(
                "Face parsing: нет файла %s. Скачайте вручную или задайте "
                "FACE_PARSING_AUTO_DOWNLOAD=1 (см. README).",
                path,
            )
            _RT.missing_model_logged = True
        return False
    url = str(
        getattr(settings, "FACE_PARSING_DOWNLOAD_URL", DEFAULT_DOWNLOAD_URL)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    logger.info("Face parsing: загрузка ONNX %s -> %s", url, path)
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "control.krmu.edu-face-parsing/1.0"},
        )
        with urllib.request.urlopen(req, timeout=600) as resp:
            data = resp.read()
        part.write_bytes(data)
        part.replace(path)
        return True
    except Exception as e:
        logger.error("Face parsing: ошибка загрузки: %s", e)
        if part.is_file():
            part.unlink(missing_ok=True)
        return False


def get_engine() -> Optional[FaceParsingEngine]:
    """
    Lazy singleton. Повтор при следующем вызове, если файла ещё не было;
    после ошибки ONNX сессии — до перезапуска процесса не пытаемся снова.
    """
    if not bool(getattr(settings, "FACE_PARSING_ENABLE", False)):
        return None
    if _RT.load_failed:
        return None
    if _RT.engine is not None:
        return _RT.engine
    with _SESSION_LOCK:
        if _RT.engine is not None:
            return _RT.engine
        if _RT.load_failed:
            return None
        path = model_path_resolved()
        if not _ensure_model_file(path):
            return None
        try:
            _RT.engine = FaceParsingEngine(path)
            logger.info("Face parsing: модель загружена из %s", path)
        except Exception as e:
            logger.error("Face parsing: не удалось открыть ONNX: %s", e)
            _RT.load_failed = True
            _RT.engine = None
    return _RT.engine


def reset_engine_cache_for_tests() -> None:
    _RT.reset()


def glasses_frac_threshold() -> float:
    return float(getattr(settings, "FACE_PARSING_GLASSES_FRAC_MIN", 0.00035))


def probe_bgr(bgr: np.ndarray) -> dict[str, Any]:
    """Метаданные для API верификации (одно фото, без датчиков)."""
    out: dict[str, Any] = {
        "face_parsing_active": False,
        "eyeglasses_likely": None,
        "eyeglasses_area_frac": None,
    }
    if not bool(getattr(settings, "FACE_PARSING_USE_FOR_API", True)):
        return out
    eng = get_engine()
    if eng is None or bgr is None or bgr.size == 0:
        return out
    try:
        m = eng.predict_mask_bgr(bgr)
        frac = eng.eyeglasses_area_frac(m)
        thr = glasses_frac_threshold()
        out["face_parsing_active"] = True
        out["eyeglasses_area_frac"] = frac
        out["eyeglasses_likely"] = bool(frac >= thr)
    except Exception as e:
        out["face_parsing_error"] = str(e)
    return out
