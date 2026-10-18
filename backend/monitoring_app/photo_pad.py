"""Photo presentation-attack check (PAD).

One question per photo: is this a live selfie, or a re-capture (phone/monitor
screen, printed photo)? A frozen CLIP ViT-L/14 embeds three views — the whole
frame squashed to a square (bezels, print edges), and its top and bottom 30%
strips enlarged (notch / status bar, messenger buttons, phone chin) — and a
logistic head trained on operator verdicts (``manage.py train_photo_pad``)
turns them into a spoof probability.

Two thresholds stored with the head split the probability into
``clean`` / ``review`` / ``suspicious``.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np
from django.conf import settings

logger = logging.getLogger(__name__)

PAD_MODEL_VERSION = "pad_clip_v2"

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

CLIP_ARCH = "ViT-L-14"
CLIP_PRETRAINED = "openai"
EMBED_DIM = 768 * 3
STRIP_FRACTION = 0.3

BRANCH_SPOOF = "clip_recapture_suspicious"
BRANCH_UNCERTAIN = "clip_uncertain_review"
BRANCH_LIVE = "clip_live_clean"

_cache: dict[str, Any] = {}
_lock = threading.Lock()


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


def normalize_device(device: Optional[str] = None) -> str:
    """Normalize the torch device hint to ``auto``, ``cpu`` or ``cuda``."""
    configured = device or getattr(settings, "PHOTO_PAD_DEVICE", DEVICE_AUTO) or DEVICE_AUTO
    normalized = str(configured).strip().lower()
    return normalized if normalized in DEVICE_VALUES else DEVICE_AUTO


def head_path() -> Path:
    return Path(settings.BASE_DIR) / "models" / "pad_clip_head.json"


def _clip(device: str = DEVICE_AUTO) -> tuple[Any, Any, Any]:
    """Load (once per process) the CLIP model, its preprocess and torch module."""
    with _lock:
        if "clip" not in _cache:
            import open_clip
            import torch

            want_cuda = device in (DEVICE_AUTO, DEVICE_CUDA) and torch.cuda.is_available()
            model, _, preprocess = open_clip.create_model_and_transforms(
                CLIP_ARCH, pretrained=CLIP_PRETRAINED
            )
            model.eval().to("cuda" if want_cuda else "cpu")
            _cache["clip"] = (model, preprocess, torch)
        return _cache["clip"]


def load_head() -> dict[str, Any]:
    """Read the trained head (coef, intercept, thresholds); cached per mtime."""
    path = head_path()
    mtime = path.stat().st_mtime
    cached = _cache.get("head")
    if cached and cached[0] == mtime:
        return cached[1]
    head = json.loads(path.read_text())
    for key in ("coef", "mean", "scale"):
        head[f"_{key}"] = np.asarray(head[key], dtype=np.float32)
    _cache["head"] = (mtime, head)
    return head


def _views(img_bgr: np.ndarray) -> list[np.ndarray]:
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    strip = max(1, int(rgb.shape[0] * STRIP_FRACTION))
    return [rgb, rgb[:strip], rgb[-strip:]]


def embed_bgr_batch(images_bgr: list[np.ndarray], device: str = DEVICE_AUTO) -> np.ndarray:
    """Features ``(n, EMBED_DIM)``: CLIP of [squashed frame | top strip | bottom strip]."""
    from PIL import Image

    model, preprocess, torch = _clip(device)
    model_device = next(model.parameters()).device
    per_view: list[list[Any]] = [[], [], []]
    for img in images_bgr:
        for k, view in enumerate(_views(img)):
            per_view[k].append(preprocess(Image.fromarray(view).resize((224, 224), Image.Resampling.BICUBIC)))
    with torch.no_grad():
        parts = [
            torch.nn.functional.normalize(model.encode_image(torch.stack(v).to(model_device)), dim=-1)
            for v in per_view
        ]
    return torch.cat(parts, dim=-1).cpu().numpy().astype(np.float32)


def spoof_probability(embedding: np.ndarray, head: Optional[dict[str, Any]] = None) -> float:
    head = head or load_head()
    x = (embedding - head["_mean"]) / head["_scale"]
    z = float(x @ head["_coef"]) + float(head["intercept"])
    return float(1.0 / (1.0 + np.exp(-z)))


_UI_REASON_RU = {
    BRANCH_SPOOF: "Похоже на пересъёмку: экран телефона/монитора или распечатанное фото.",
    BRANCH_UNCERTAIN: "Модель не уверена, живое ли это фото. Нужна проверка оператора.",
}


def verdict_from_probability(p: float, head: dict[str, Any], elapsed_ms: float = 0.0) -> PadResult:
    """Map spoof probability to status using the head's calibrated thresholds."""
    t_clean = float(head["t_clean"])
    t_susp = float(head["t_suspicious"])
    if p >= t_susp:
        status, trust, branch = STATUS_SUSPICIOUS, False, BRANCH_SPOOF
    elif p <= t_clean:
        status, trust, branch = STATUS_CLEAN, True, BRANCH_LIVE
    else:
        status, trust, branch = STATUS_REVIEW, None, BRANCH_UNCERTAIN
    struct = {
        "schema": "pad_clip_v1",
        "branch": branch,
        "status": status,
        "spoof_probability": round(p, 4),
        "t_clean": t_clean,
        "t_suspicious": t_susp,
        "head_trained_at": head.get("trained_at", ""),
    }
    tags = [
        f"pad_rule:{branch}",
        f"pad_evidence:df={p:.3f}",
        f"pad_struct:{json.dumps(struct, separators=(',', ':'))}",
    ]
    if branch in _UI_REASON_RU:
        tags.append(f"pad_ui_reason:{_UI_REASON_RU[branch]}")
    return PadResult(
        status=status,
        trust_confirmed=trust,
        risk_score=p,
        tags=tags,
        elapsed_ms=elapsed_ms,
        deepface_score=p,
    )


def check_photo_bgr(img_bgr: np.ndarray, device: Optional[str] = None) -> PadResult:
    started = time.monotonic()
    head = load_head()
    p = spoof_probability(embed_bgr_batch([img_bgr], normalize_device(device))[0], head)
    return verdict_from_probability(p, head, (time.monotonic() - started) * 1000.0)


def check_photo(image_path: str | Path, device: Optional[str] = None) -> PadResult:
    img_bgr = cv2.imread(str(image_path))
    if img_bgr is None:
        return PadResult(
            status=STATUS_ERROR, trust_confirmed=None, risk_score=0.0, tags=["decode_error"]
        )
    return check_photo_bgr(img_bgr, device=device)
