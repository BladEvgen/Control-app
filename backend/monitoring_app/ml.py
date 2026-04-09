import contextlib
import importlib
import io
import json
import logging
import os
import traceback
from collections import Counter
from collections.abc import Iterable
from threading import Lock
from typing import Any, Optional, cast

import numpy as np
import torch
import torch.nn as nn
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from monitoring_app import models
from rest_framework.exceptions import ValidationError
from sklearn.metrics import f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.neighbors import NearestNeighbors
from sklearn.utils.class_weight import compute_class_weight
from torch.optim.adamw import AdamW
from torch.utils.data import DataLoader, TensorDataset, WeightedRandomSampler

cv2 = cast(Any, importlib.import_module("cv2"))


def imread_bgr(path: str) -> Optional[np.ndarray]:
    """
    Чтение BGR для ArcFace. Сначала OpenCV; если не вышло — PIL (битые/усечённые JPEG).
    """
    image = cv2.imread(path, cv2.IMREAD_COLOR)
    if image is not None:
        return image
    try:
        from PIL import Image, ImageFile

        ImageFile.LOAD_TRUNCATED_IMAGES = True
        with Image.open(path) as im:
            im = im.convert("RGB")
            rgb = np.asarray(im)
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except Exception as exc:
        logger.warning("imread_bgr PIL fallback failed for %s: %s", path, exc)
        return None


def _get_face_analysis():
    try:
        from insightface.app import FaceAnalysis

        return FaceAnalysis
    except ImportError as e:
        raise ImportError(
            "insightface не установлен. На Windows установите Visual C++ Build Tools, "
            "затем: pip install -r requirements_win_optional.txt"
        ) from e


# -----------------------------------
# 1. Logging Setup
# -----------------------------------

logger = logging.getLogger("django")


def _sklearn_stratify_y(y: np.ndarray) -> Optional[np.ndarray]:
    """Stratify только если в каждом классе ≥2 примеров (иначе sklearn падает)."""
    y_np = np.asarray(y).ravel()
    if y_np.size < 4:
        return None
    _u, counts = np.unique(y_np, return_counts=True)
    if counts.size == 0 or int(counts.min()) < 2:
        return None
    return y_np


def _general_model_meta_path() -> str:
    root = getattr(settings, "GENERAL_MODELS_ROOT", "")
    return os.path.join(root, "general_face_model_meta.json")


def _apply_general_checkpoint_partial(
    model: "GeneralFaceRecognitionModel",
    ckpt: dict[str, torch.Tensor],
    old_nc: int,
    _new_nc: int,
) -> None:
    """Копирует веса с предыдущей общей модели; fc3 расширяется при добавлении классов."""
    sd = model.state_dict()
    for k, v in ckpt.items():
        if k not in sd:
            continue
        if k == "fc3.weight":
            take = min(int(old_nc), int(v.shape[0]), int(sd[k].shape[0]))
            sd[k][:take].copy_(v[:take])
            if sd[k].shape[0] > take:
                nn.init.normal_(sd[k][take:], 0.0, 0.02)
        elif k == "fc3.bias":
            take = min(int(old_nc), int(v.shape[0]), int(sd[k].shape[0]))
            sd[k][:take].copy_(v[:take])
            if sd[k].shape[0] > take:
                sd[k][take:].zero_()
        elif tuple(v.shape) == tuple(sd[k].shape):
            sd[k].copy_(v)
    model.load_state_dict(sd)


# -----------------------------------
# 2. Global Variables and Device Setup
# -----------------------------------


class _ArcFaceModelHolder:
    instance: Optional[Any] = None


arcface_model_holder = _ArcFaceModelHolder()

arcface_lock = Lock()
runtime_gallery_cache_lock = Lock()

RUNTIME_GALLERY_CACHE_VERSION = 2
_staff_runtime_gallery_mem_cache: dict[
    str, tuple[str, Optional[np.ndarray], dict[str, int]]
] = {}
_multi_staff_runtime_gallery_mem_cache: Optional[
    tuple[tuple[str, ...], np.ndarray, tuple[str, ...]]
] = None


class _ArcfacePrepareCache:
    """Последний det_size для FaceAnalysis.prepare — не вызывать prepare повторно зря."""

    det_size: Optional[tuple[int, int]] = None


def _arcface_prepare_det(model: Any, ctx_id: int, det_size: tuple[int, int]) -> None:
    if _ArcfacePrepareCache.det_size == det_size:
        return
    from monitoring_app.ml_log_quiet import ml_third_party_stdout_verbose

    _stdout_ctx: contextlib.AbstractContextManager[Any] = (
        contextlib.nullcontext()
        if ml_third_party_stdout_verbose()
        else contextlib.redirect_stdout(io.StringIO())
    )
    with _stdout_ctx:
        model.prepare(ctx_id=ctx_id, det_size=det_size)
    _ArcfacePrepareCache.det_size = det_size


def get_device():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Selected device: {device}")
    return device


def load_arcface_model():
    if arcface_model_holder.instance is None:
        with arcface_lock:
            if arcface_model_holder.instance is None:
                from monitoring_app.ml_log_quiet import ml_third_party_stdout_verbose

                FaceAnalysis = _get_face_analysis()
                cuda_available = torch.cuda.is_available()
                device_type = "GPU" if cuda_available else "CPU"
                logger.info(f"Using {device_type} for ArcFace model")
                providers = (
                    ["CUDAExecutionProvider", "CPUExecutionProvider"]
                    if cuda_available
                    else ["CPUExecutionProvider"]
                )
                _stdout_ctx: contextlib.AbstractContextManager[Any] = (
                    contextlib.nullcontext()
                    if ml_third_party_stdout_verbose()
                    else contextlib.redirect_stdout(io.StringIO())
                )
                with _stdout_ctx:
                    model = FaceAnalysis(
                        name="buffalo_l",
                        providers=providers,
                    )
                    ctx_id = 0 if cuda_available else -1
                    model.prepare(ctx_id=ctx_id, det_size=(640, 640))
                _ArcfacePrepareCache.det_size = (640, 640)
                arcface_model_holder.instance = model


def _runtime_gallery_cache_dir() -> str:
    """Return directory for persisted runtime gallery caches.

    Returns:
        Absolute cache directory path.
    """
    root = os.path.join(settings.MEDIA_ROOT, "_face_runtime_cache")
    os.makedirs(root, exist_ok=True)
    return root


def _runtime_gallery_file_signature(path: Optional[str]) -> Optional[str]:
    """Build a cheap signature for a source file.

    Args:
        path: Absolute file path or None.

    Returns:
        ``mtime:size`` signature or None when file is absent.
    """
    if not path or not os.path.isfile(path):
        return None
    stat = os.stat(path)
    return f"{stat.st_mtime_ns}:{stat.st_size}"


def _staff_runtime_gallery_signature(staff: "models.Staff") -> str:
    """Describe all runtime gallery sources for one staff row.

    Args:
        staff: Staff row used for verify/search gallery.

    Returns:
        Stable JSON signature for cache validation.
    """
    avatar_path: Optional[str] = None
    gallery_real_path: Optional[str] = None
    try:
        if staff.avatar and getattr(staff.avatar, "path", None):
            avatar_path = staff.avatar.path
            gallery_real_path = os.path.join(
                os.path.dirname(staff.avatar.path), f"{staff.pin}_gallery_real.npy"
            )
    except Exception:
        avatar_path = None
        gallery_real_path = None

    mask_updated: Optional[str] = None
    mask_present = False
    try:
        fm = staff.face_mask
        if fm is not None and fm.mask_encoding:
            mask_present = True
            if fm.updated_at is not None:
                mask_updated = fm.updated_at.isoformat()
    except ObjectDoesNotExist:
        mask_present = False

    payload = {
        "pin": staff.pin,
        "avatar": _runtime_gallery_file_signature(avatar_path),
        "gallery_real": _runtime_gallery_file_signature(gallery_real_path),
        "mask_present": mask_present,
        "mask_updated": mask_updated,
        "version": RUNTIME_GALLERY_CACHE_VERSION,
    }
    return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _staff_runtime_gallery_cache_path(pin: str) -> str:
    """Return file path for one staff runtime gallery cache.

    Args:
        pin: Staff PIN.

    Returns:
        Absolute ``.npz`` path.
    """
    safe_pin = "".join(ch if ch.isalnum() else "_" for ch in pin.upper())
    return os.path.join(
        _runtime_gallery_cache_dir(),
        f"{safe_pin}_runtime_gallery_v{RUNTIME_GALLERY_CACHE_VERSION}.npz",
    )


def _multi_staff_runtime_gallery_cache_path() -> str:
    """Return file path for the global search gallery cache.

    Returns:
        Absolute ``.npz`` path.
    """
    return os.path.join(
        _runtime_gallery_cache_dir(),
        f"runtime_search_gallery_v{RUNTIME_GALLERY_CACHE_VERSION}.npz",
    )


def _load_staff_runtime_gallery_cache(
    cache_path: str,
    signature: str,
) -> Optional[tuple[Optional[np.ndarray], dict[str, int]]]:
    """Load one-staff runtime gallery from disk when signature matches.

    Args:
        cache_path: Cache file path.
        signature: Current signature for this staff row.

    Returns:
        Cached matrix + breakdown, or None when cache is stale/unreadable.
    """
    if not os.path.isfile(cache_path):
        return None
    try:
        with np.load(cache_path, allow_pickle=False) as data:
            cached_signature = str(data["signature"].tolist())
            if cached_signature != signature:
                return None
            breakdown = json.loads(str(data["breakdown_json"].tolist()))
            has_gallery = bool(int(data["has_gallery"].tolist()))
            if not has_gallery:
                return None, breakdown
            gallery = np.asarray(data["gallery"], dtype=np.float64)
            if gallery.ndim == 1:
                gallery = gallery.reshape(1, -1)
            return gallery, breakdown
    except Exception:
        return None


def _save_staff_runtime_gallery_cache(
    cache_path: str,
    signature: str,
    gallery: Optional[np.ndarray],
    breakdown: dict[str, int],
) -> None:
    """Persist one-staff runtime gallery cache to disk.

    Args:
        cache_path: Cache file path.
        signature: Source signature.
        gallery: L2-normalized matrix or None.
        breakdown: Prototype counts by source.
    """
    payload: dict[str, Any] = {
        "signature": np.asarray(signature),
        "breakdown_json": np.asarray(
            json.dumps(breakdown, ensure_ascii=True, sort_keys=True)
        ),
        "has_gallery": np.asarray(1 if gallery is not None and gallery.size else 0),
    }
    if gallery is not None and gallery.size:
        payload["gallery"] = np.asarray(gallery, dtype=np.float32)
    tmp_path = f"{cache_path}.tmp"
    with open(tmp_path, "wb") as tmp_file:
        np.savez(tmp_file, **payload)
    os.replace(tmp_path, cache_path)


def _load_multi_staff_runtime_gallery_cache(
    cache_path: str,
    staff_list: list["models.Staff"],
) -> Optional[tuple[np.ndarray, list["models.Staff"]]]:
    """Load cached 1:N search gallery when current staff set matches.

    Args:
        cache_path: Cache file path.
        staff_list: Current searchable staff rows.

    Returns:
        Cached matrix and owner rows, or None when cache is stale/unreadable.
    """
    if not os.path.isfile(cache_path):
        return None
    staff_by_pin = {staff.pin: staff for staff in staff_list}
    current_pins = tuple(staff_by_pin.keys())
    try:
        with np.load(cache_path, allow_pickle=False) as data:
            cached_staff_pins = tuple(str(v) for v in data["staff_pins"].tolist())
            if cached_staff_pins != current_pins:
                return None
            owner_pins = tuple(str(v) for v in data["owner_pins"].tolist())
            if any(pin not in staff_by_pin for pin in owner_pins):
                return None
            matrix = np.asarray(data["matrix"], dtype=np.float64)
            owners = [staff_by_pin[pin] for pin in owner_pins]
            return matrix, owners
    except Exception:
        return None


def _load_cached_runtime_gallery_only(
    staff: "models.Staff",
) -> Optional[tuple[Optional[np.ndarray], dict[str, int]]]:
    """Load one-staff gallery only from already prepared caches.

    Args:
        staff: Staff row to probe.

    Returns:
        Cached gallery payload or None when nothing is prepared yet.
    """
    signature = _staff_runtime_gallery_signature(staff)
    mem_cached = _staff_runtime_gallery_mem_cache.get(staff.pin)
    if mem_cached and mem_cached[0] == signature:
        return mem_cached[1], dict(mem_cached[2])
    cache_path = _staff_runtime_gallery_cache_path(staff.pin)
    disk_cached = _load_staff_runtime_gallery_cache(cache_path, signature)
    if disk_cached is not None:
        gallery, breakdown = disk_cached
        _staff_runtime_gallery_mem_cache[staff.pin] = (
            signature,
            gallery,
            dict(breakdown),
        )
    return disk_cached


def build_cached_staff_runtime_gallery_matrix(
    staff_iterable: Iterable["models.Staff"],
) -> tuple[np.ndarray, list["models.Staff"]]:
    """Stack only already cached runtime prototypes for fast early search.

    Args:
        staff_iterable: Searchable staff rows.

    Returns:
        Matrix and owner rows from existing caches only.

    Raises:
        ValueError: When no cached staff galleries exist yet.
    """
    owners: list[models.Staff] = []
    blocks: list[np.ndarray] = []
    for staff in staff_iterable:
        cached = _load_cached_runtime_gallery_only(staff)
        if cached is None:
            continue
        gal, _breakdown = cached
        if gal is None or gal.size == 0:
            continue
        for i in range(int(gal.shape[0])):
            owners.append(staff)
            blocks.append(gal[i : i + 1])
    if not blocks:
        raise ValueError("No cached runtime gallery prototypes available.")
    return np.vstack(blocks), owners


def _save_multi_staff_runtime_gallery_cache(
    cache_path: str,
    staff_pins: tuple[str, ...],
    matrix: np.ndarray,
    owner_pins: tuple[str, ...],
) -> None:
    """Persist the full 1:N search gallery to disk.

    Args:
        cache_path: Cache file path.
        staff_pins: Ordered searchable staff pins.
        matrix: L2-normalized prototype matrix.
        owner_pins: Prototype owner pin for each row.
    """
    tmp_path = f"{cache_path}.tmp"
    with open(tmp_path, "wb") as tmp_file:
        np.savez(
            tmp_file,
            staff_pins=np.asarray(staff_pins),
            owner_pins=np.asarray(owner_pins),
            matrix=np.asarray(matrix, dtype=np.float32),
        )
    os.replace(tmp_path, cache_path)


def invalidate_runtime_gallery_caches(staff_pin: Optional[str] = None) -> None:
    """Drop persisted and in-memory runtime gallery caches.

    Args:
        staff_pin: Optional PIN whose per-staff cache should be removed too.
    """
    global _multi_staff_runtime_gallery_mem_cache
    with runtime_gallery_cache_lock:
        _multi_staff_runtime_gallery_mem_cache = None
        if staff_pin:
            _staff_runtime_gallery_mem_cache.pop(staff_pin, None)
            staff_cache = _staff_runtime_gallery_cache_path(staff_pin)
            if os.path.isfile(staff_cache):
                try:
                    os.remove(staff_cache)
                except OSError:
                    pass
        else:
            _staff_runtime_gallery_mem_cache.clear()
        global_cache = _multi_staff_runtime_gallery_cache_path()
        if os.path.isfile(global_cache):
            try:
                os.remove(global_cache)
            except OSError:
                pass


# -----------------------------------
# 3. Image Processing Functions
# -----------------------------------


def load_image_from_memory(file):
    """
    Loads an image from memory into a NumPy array.

    Args:
        file (InMemoryUploadedFile): Uploaded image file.

    Returns:
        numpy.ndarray: Image array.

    Raises:
        ValidationError: If the image cannot be read.
    """
    try:
        file_bytes = np.frombuffer(file.read(), np.uint8)
        image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        if image is None:
            raise ValidationError("Невозможно прочитать изображение.")
        return image
    except Exception as e:
        logger.error(f"Ошибка при чтении изображения: {e}")
        raise ValidationError(f"Ошибка чтения изображения: {str(e)}")


def _staff_upload_megapixel_guard(image_bgr: np.ndarray) -> None:
    h, w = int(image_bgr.shape[0]), int(image_bgr.shape[1])
    max_mp = int(getattr(settings, "STAFF_UPLOAD_MAX_MEGAPIXELS", 36))
    if h <= 0 or w <= 0:
        raise ValidationError("Некорректный размер изображения.")
    if h * w > max_mp * 1_000_000:
        raise ValidationError("Слишком большое разрешение изображения.")


def decode_upload_image_bytes_to_bgr(raw_bytes: bytes) -> np.ndarray:
    """
    Decode an uploaded still image to BGR ``uint8`` (OpenCV first, PIL fallback).

    Used before PAD / face pipelines and before re-encoding to canonical JPEG.
    """
    if not raw_bytes:
        raise ValidationError("Пустой файл изображения.")
    buf = np.frombuffer(bytearray(raw_bytes), dtype=np.uint8)
    image = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if image is None:
        try:
            from io import BytesIO

            from PIL import Image

            with Image.open(BytesIO(raw_bytes)) as im:
                im = im.convert("RGB")
                rgb = np.asarray(im, dtype=np.uint8)
            image = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        except Exception as exc:
            logger.warning(
                "decode_upload_image_bytes_to_bgr PIL fallback failed: %s", exc
            )
            raise ValidationError("Невозможно прочитать изображение.") from exc
    _staff_upload_megapixel_guard(image)
    return image


def reencode_bgr_to_canonical_jpeg_bytes(
    image_bgr: np.ndarray,
    *,
    quality: int | None = None,
) -> bytes:
    """
    Encode a BGR image as baseline JPEG — canonical on-disk format for staff uploads.
    """
    q = (
        quality
        if quality is not None
        else int(getattr(settings, "STAFF_UPLOAD_JPEG_QUALITY", 92))
    )
    q = max(1, min(100, int(q)))
    ok, enc = cv2.imencode(".jpg", image_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), q])
    if not ok or enc is None:
        raise ValidationError("Не удалось нормализовать изображение до JPEG.")
    return enc.tobytes()


def preprocess_image(image):
    """
    Resizes the image if its dimensions are smaller than 640x640.

    Args:
        image (numpy.ndarray): Image array.

    Returns:
        numpy.ndarray: Preprocessed image array.

    Raises:
        ValueError: If the input is not a NumPy array.
    """
    if not isinstance(image, np.ndarray):
        raise ValueError("Expected image as numpy array, got different format.")

    height, width = image.shape[:2]
    if height < 640 or width < 640:
        scale_factor = max(640 / height, 640 / width)
        new_size = (int(width * scale_factor), int(height * scale_factor))
        image = cv2.resize(image, new_size, interpolation=cv2.INTER_CUBIC)
    return image


def _bbox_area_insight(bbox) -> float:
    try:
        x1, y1, x2, y2 = (float(bbox[i]) for i in range(4))
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)
    except (TypeError, ValueError, IndexError):
        return 0.0


def _arcface_get_faces(image_bgr: np.ndarray) -> list:
    """
    Детекция лиц ArcFace; при пустом результате — повтор с большим det_size
    (мелкое или сильно повёрнутое лицо).
    """
    load_arcface_model()
    model = arcface_model_holder.instance
    if model is None or not isinstance(image_bgr, np.ndarray):
        return []
    img = preprocess_image(image_bgr)
    cuda_available = torch.cuda.is_available()
    ctx_id = 0 if cuda_available else -1
    with arcface_lock:
        faces = model.get(img)
        if faces:
            return list(faces)
        for det_sz in ((960, 960), (1280, 1280)):
            try:
                _arcface_prepare_det(model, ctx_id, det_sz)
                faces = model.get(img)
            except Exception as e:
                logger.warning("ArcFace det_size=%s: %s", det_sz, e)
                faces = []
            finally:
                try:
                    _arcface_prepare_det(model, ctx_id, (640, 640))
                except Exception:
                    pass
            if faces:
                return list(faces)
    return []


def _largest_insight_face(faces: list) -> Optional[Any]:
    if not faces:
        return None
    return max(faces, key=lambda f: _bbox_area_insight(f.bbox))


# -----------------------------------
# 4. Embedding Creation Functions
# -----------------------------------


def _lesson_attendance_stored_path_allowed(abs_path: str) -> bool:
    """Return True if ``abs_path`` is under attendance or control_image media roots.

    Mirrors the path allowlist used in admin when handling lesson photo files.

    Args:
        abs_path: Normalized absolute filesystem path string.

    Returns:
        Whether the path is confined to ``ATTENDANCE_ROOT`` or
        ``MEDIA_ROOT/control_image``.
    """
    if not abs_path:
        return False
    try:
        normalized = os.path.abspath(str(abs_path))
    except OSError:
        return False
    attendance_root = os.path.abspath(str(settings.ATTENDANCE_ROOT))
    media_control_root = os.path.abspath(
        os.path.join(str(settings.MEDIA_ROOT), "control_image")
    )
    for root in (attendance_root, media_control_root):
        if normalized == root or normalized.startswith(f"{root}{os.sep}"):
            return True
    return False


def _collect_readable_lesson_attendance_paths_for_staff(
    staff: "models.Staff",
) -> list[str]:
    """Collect absolute paths to lesson attendance photos usable for embeddings.

    Selects ``LessonAttendance`` rows with a trusted verdict (manual clean, or
    auto clean with no manual override) and excludes manual suspicious. Paths
    must exist, stay under allowed roots, and decode as images via ``imread_bgr``.
    A manual "clean" verdict does not imply the file is intact; broken files are
    skipped so they never enter training.

    Files are **not** copied into ``AUGMENT_ROOT``; only paths are returned and
    read during ``create_embeddings_from_images`` (vectors live in memory until
    ``embeddings.npy`` is written).

    Args:
        staff: ``Staff`` instance.

    Returns:
        Up to ``FACE_TRAINING_LESSON_ATTENDANCE_MAX`` distinct readable paths.
    """
    if not getattr(settings, "FACE_TRAINING_INCLUDE_LESSON_ATTENDANCE", True):
        return []
    la = models.LessonAttendance
    qs = (
        la.objects.filter(staff=staff, staff_image_path__isnull=False)
        .exclude(staff_image_path="")
        .filter(
            Q(photo_manual_verdict=la.PHOTO_MANUAL_VERDICT_CLEAN)
            | (
                Q(photo_manual_verdict=la.PHOTO_MANUAL_VERDICT_NONE)
                & Q(photo_spoof_status=la.PHOTO_SPOOF_STATUS_CLEAN)
            )
        )
        .exclude(photo_manual_verdict=la.PHOTO_MANUAL_VERDICT_SUSPICIOUS)
        .order_by("-date_at", "-first_in", "-id")
    )
    cap = max(0, int(getattr(settings, "FACE_TRAINING_LESSON_ATTENDANCE_MAX", 80)))
    if cap == 0:
        return []

    seen: set[str] = set()
    out: list[str] = []
    skipped_bad_path = 0
    skipped_missing = 0
    skipped_unreadable = 0

    for row in qs[: cap * 3].iterator(chunk_size=100):
        raw = (row.staff_image_path or "").strip()
        if not raw:
            continue
        if not _lesson_attendance_stored_path_allowed(raw):
            skipped_bad_path += 1
            continue
        abs_path = os.path.abspath(str(raw))
        if abs_path in seen:
            continue
        if not os.path.isfile(abs_path):
            skipped_missing += 1
            logger.info(
                "LessonAttendance id=%s: файл фото отсутствует на диске, пропуск для обучения: %s",
                row.pk,
                abs_path,
            )
            continue
        if imread_bgr(abs_path) is None:
            skipped_unreadable += 1
            logger.warning(
                "LessonAttendance id=%s: фото не читается (битый/пустой файл), пропуск: %s",
                row.pk,
                abs_path,
            )
            continue
        seen.add(abs_path)
        out.append(abs_path)
        if len(out) >= cap:
            break

    logger.info(
        "lesson_attendance paths for %s: added %s (cap=%s, skipped path_outside=%s missing=%s unreadable=%s)",
        staff.pin,
        len(out),
        cap,
        skipped_bad_path,
        skipped_missing,
        skipped_unreadable,
    )
    return out


def _collect_trusted_staff_face_sample_paths_for_staff(
    staff: "models.Staff",
) -> list[str]:
    """Paths for active trusted :class:`~monitoring_app.models.StaffFaceSample` images."""
    cap = max(0, int(getattr(settings, "FACE_BOOTSTRAP_MAX_ACTIVE_SAMPLES", 5)))
    if cap == 0:
        return []
    out: list[str] = []
    seen: set[str] = set()
    qs = models.StaffFaceSample.objects.filter(
        staff=staff, is_active=True, is_trusted=True
    ).order_by("-created_at")
    for row in qs.iterator(chunk_size=50):
        if len(out) >= cap:
            break
        f = row.image
        p = getattr(f, "path", "") or ""
        if not p or not os.path.isfile(p):
            continue
        ap = os.path.abspath(p)
        if ap in seen:
            continue
        seen.add(ap)
        out.append(p)
    return out


def create_embeddings_for_staff(staff):
    """Compute and save ``{pin}_embeddings.npy`` next to the staff avatar.

    Concatenates paths from: avatar file, images under ``AUGMENT_ROOT``, and
    optionally lesson attendance photos (see
    ``FACE_TRAINING_INCLUDE_LESSON_ATTENDANCE``). Attendance images are read from
    their original paths only; they are **not** copied into the augment folder.
    Embeddings are built in memory then persisted as a single ``.npy`` file.

    Args:
        staff: ``Staff`` with a valid ``avatar`` on disk.

    Raises:
        ValueError: If the avatar is missing or no embeddings could be produced.
    """
    try:
        if not staff.avatar or not os.path.exists(staff.avatar.path):
            logger.error(f"Avatar отсутствует для {staff.pin}")
            raise ValueError(f"Avatar отсутствует для {staff.pin}")

        avatar_image_path = str(staff.avatar.path)
        augmented_image_dir = str(settings.AUGMENT_ROOT).format(staff_pin=staff.pin)

        if not os.path.exists(augmented_image_dir):
            logger.warning(
                f"Директория аугментации не найдена: {augmented_image_dir}",
            )
            augmented_images = []
        else:
            augmented_images = [
                os.path.join(augmented_image_dir, img)
                for img in os.listdir(augmented_image_dir)
                if img.endswith((".png", ".jpg", ".jpeg"))
            ]

        lesson_paths = _collect_readable_lesson_attendance_paths_for_staff(staff)
        all_image_paths = [avatar_image_path] + augmented_images + lesson_paths

        embeddings = create_embeddings_from_images(all_image_paths)

        if not embeddings:
            logger.error(f"Не удалось создать эмбеддинги для {staff.pin}")
            raise ValueError(f"Не удалось создать эмбеддинги для {staff.pin}")

        embeddings_path = os.path.join(
            os.path.dirname(avatar_image_path), f"{staff.pin}_embeddings.npy"
        )
        np.save(embeddings_path, embeddings)
        logger.info(
            f"Сохранены эмбеддинги для {staff.pin} по пути {embeddings_path}",
        )

    except Exception as e:
        logger.error(
            f"Ошибка при создании эмбеддингов для {staff.pin}: {str(e)}\n{traceback.format_exc()}",
        )
        raise e


def create_embeddings_from_images(image_paths):
    """Create ArcFace embeddings for each readable image path.

    Paths may include the avatar, files under ``AUGMENT_ROOT``, and any other
    absolute image paths (e.g. lesson attendance photos); images are loaded
    from disk per call—nothing is copied into the augment directory here.

    Drops outliers whose cosine similarity to the L2-normalized geometric median
    direction is below ``FACE_EMBEDDING_OUTLIER_COS_MIN`` (default ``0.35``). If
    filtering would remove all rows, returns every successfully computed
    embedding.

    Args:
        image_paths: Iterable of absolute paths to image files.

    Returns:
        List of embedding vectors (each a ``list`` of ``float``).
    """
    min_cos = float(getattr(settings, "FACE_EMBEDDING_OUTLIER_COS_MIN", 0.35))
    raw_paths: list[str] = []
    raw_vecs: list[np.ndarray] = []

    for image_path in image_paths:
        if not os.path.exists(image_path):
            logger.warning("Image file does not exist: %s", image_path)
            continue

        image = imread_bgr(image_path)
        if image is None:
            logger.warning("Failed to load image (possibly corrupted): %s", image_path)
            continue

        image = preprocess_image(image)
        embedding = create_face_encoding(image)
        if embedding is not None:
            raw_paths.append(image_path)
            raw_vecs.append(np.asarray(embedding, dtype=np.float64))
        else:
            logger.warning("Failed to create embedding for image: %s", image_path)

    n = len(raw_vecs)
    logger.info(
        "create_embeddings_from_images: %s paths, %s embeddings before filter",
        len(image_paths),
        n,
    )
    if n == 0:
        return []
    if n <= 2:
        return [v.tolist() for v in raw_vecs]

    mat = np.stack(raw_vecs, axis=0)
    median_vec = np.median(mat, axis=0)
    median_norm = np.linalg.norm(median_vec)
    if median_norm < 1e-8:
        return [v.tolist() for v in raw_vecs]
    median_unit = median_vec / median_norm

    kept: list[np.ndarray] = []
    dropped = 0
    for path, vec in zip(raw_paths, raw_vecs):
        vn = np.linalg.norm(vec)
        if vn < 1e-8:
            dropped += 1
            logger.warning("Zero-norm embedding dropped: %s", path)
            continue
        cos = float(np.dot(vec / vn, median_unit))
        if cos >= min_cos:
            kept.append(vec)
        else:
            dropped += 1
            logger.warning(
                "Outlier embedding dropped: %s cosine_to_median=%.4f (min=%.4f)",
                path,
                cos,
                min_cos,
            )

    if not kept:
        logger.warning(
            "All embeddings marked outliers; keeping unfiltered set of %s",
            n,
        )
        return [v.tolist() for v in raw_vecs]

    logger.info(
        "Embedding filter: kept %s / %s (dropped %s)",
        len(kept),
        n,
        dropped,
    )
    return [v.tolist() for v in kept]


def create_face_encoding(image_or_path):
    """
    Creates a face embedding using the ArcFace model.

    Args:
        image_or_path (numpy.ndarray or str): Image array or image file path.

    Returns:
        list or None: Face embedding or None if failed.
    """
    try:
        load_arcface_model()
        if isinstance(image_or_path, str):
            if not os.path.exists(image_or_path):
                logger.warning(f"Image file not found: {image_or_path}")
                return None

            image = imread_bgr(image_or_path)
            if image is None:
                logger.warning(f"Failed to load image: {image_or_path}")
                return None

            image = preprocess_image(image)
        else:
            if not isinstance(image_or_path, np.ndarray):
                logger.warning("Invalid image format, expected numpy array.")
                return None
            image = image_or_path

        faces = _arcface_get_faces(image)
        face = _largest_insight_face(faces)
        if face is None:
            logger.warning("No face detected in image %s", str(image_or_path))
            return None

        return face.embedding.tolist()

    except Exception as e:
        logger.error(f"Ошибка при создании encoding: {e}")
        return None


def create_face_encoding_with_probe_meta(
    image_bgr: np.ndarray,
) -> tuple[Optional[list[float]], dict[str, object]]:
    """
    ArcFace embedding plus conservative probe quality hints (BGR image).

    Returns:
        (embedding list or None, meta with quality_pass, det_score, face_area_ratio, ...).
    """
    try:
        load_arcface_model()
        if not isinstance(image_bgr, np.ndarray):
            return None, {"face_present": False, "quality_pass": False}

        faces = _arcface_get_faces(image_bgr)
        face = _largest_insight_face(faces)
        if face is None:
            return None, {"face_present": False, "quality_pass": False}

        det_raw = getattr(face, "det_score", None)
        det_f = float(det_raw) if det_raw is not None else None
        bbox = face.bbox
        h, w = int(image_bgr.shape[0]), int(image_bgr.shape[1])
        area = _bbox_area_insight(bbox)
        denom = float(max(1, h * w))
        face_ratio = float(area) / denom

        min_det = float(getattr(settings, "FACE_VERIFY_PROBE_DET_SCORE_MIN", 0.35))
        min_face = float(
            getattr(settings, "FACE_VERIFY_PROBE_FACE_AREA_RATIO_MIN", 0.008)
        )
        quality_pass = True
        qreasons: list[str] = []
        if det_f is not None and det_f < min_det:
            quality_pass = False
            qreasons.append("low_det_score")
        if face_ratio < min_face:
            quality_pass = False
            qreasons.append("small_face")

        return face.embedding.tolist(), {
            "face_present": True,
            "det_score": det_f,
            "face_area_ratio": face_ratio,
            "quality_pass": quality_pass,
            "quality_reason_codes": qreasons,
        }
    except Exception as e:
        logger.error("create_face_encoding_with_probe_meta: %s", e)
        return None, {"face_present": False, "quality_pass": False}


def _l2_normalize_embedding_rows(mat: np.ndarray) -> np.ndarray:
    mat = np.asarray(mat, dtype=np.float64)
    if mat.ndim == 1:
        mat = mat.reshape(1, -1)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-10)
    return mat / norms


def _probe_embedding_row(embedding) -> np.ndarray:
    """Вектор лица (1D) из ArcFace; без «схлопывания» в (dim,) при одном лице."""
    v = np.asarray(embedding, dtype=np.float64)
    if v.size == 0:
        raise ValueError("Пустой эмбеддинг лица")
    return v.reshape(-1)


def _staff_mask_encoding_row(mask_encoding) -> np.ndarray:
    """Один ряд эмбеддинга сотрудника из JSON/маски (часто list или [[...]])."""
    v = np.asarray(mask_encoding, dtype=np.float64)
    if v.size == 0:
        raise ValueError("Пустая маска лица")
    if v.ndim > 1:
        v = np.asarray(v[0], dtype=np.float64).reshape(-1)
    else:
        v = v.reshape(-1)
    return v


def _dedupe_normalized_rows(mat: np.ndarray, min_cos: float = 0.999) -> np.ndarray:
    """Drop near-duplicate prototypes (same face stored multiple times)."""
    if mat.shape[0] <= 1:
        return mat
    keep_indices: list[int] = [0]
    for i in range(1, mat.shape[0]):
        sims = mat[i : i + 1] @ mat[keep_indices].T
        if float(np.max(sims)) < min_cos:
            keep_indices.append(i)
    return mat[keep_indices]


def _mask_json_to_matrix(mask_encoding: Any) -> Optional[np.ndarray]:
    if mask_encoding is None:
        return None
    try:
        m = np.asarray(mask_encoding, dtype=np.float64)
    except (TypeError, ValueError):
        return None
    if m.size == 0:
        return None
    if m.ndim == 1:
        return m.reshape(1, -1)
    if m.ndim == 2:
        return m
    return m.reshape(-1, m.shape[-1])


def build_runtime_gallery_embeddings(
    staff: "models.Staff",
) -> tuple[Optional[np.ndarray], dict[str, int]]:
    """
    Runtime gallery only: stored mask, live avatar file, optional ``{pin}_gallery_real.npy``.

    Train-only ``embeddings.npy`` is never loaded here.
    Rows are L2-normalized and near-duplicate collapsed.
    """
    signature = _staff_runtime_gallery_signature(staff)
    mem_cached = _staff_runtime_gallery_mem_cache.get(staff.pin)
    if mem_cached and mem_cached[0] == signature:
        return mem_cached[1], dict(mem_cached[2])

    cache_path = _staff_runtime_gallery_cache_path(staff.pin)
    disk_cached = _load_staff_runtime_gallery_cache(cache_path, signature)
    if disk_cached is not None:
        gallery, breakdown = disk_cached
        _staff_runtime_gallery_mem_cache[staff.pin] = (
            signature,
            gallery,
            dict(breakdown),
        )
        return gallery, dict(breakdown)

    rows: list[np.ndarray] = []
    breakdown: dict[str, int] = {
        "mask_prototypes": 0,
        "avatar_prototypes": 0,
        "gallery_real_npy_prototypes": 0,
    }

    try:
        fm = staff.face_mask
        if fm is not None and fm.mask_encoding:
            mm = _mask_json_to_matrix(fm.mask_encoding)
            if mm is not None:
                rows.append(mm)
                breakdown["mask_prototypes"] = int(mm.shape[0])
    except ObjectDoesNotExist:
        pass

    try:
        if staff.avatar and getattr(staff.avatar, "path", None):
            ap = staff.avatar.path
            if ap and os.path.isfile(ap):
                enc = create_face_encoding(ap)
                if enc is not None:
                    rows.append(np.asarray(enc, dtype=np.float64).reshape(1, -1))
                    breakdown["avatar_prototypes"] = 1
    except Exception as e:
        logger.warning(
            "Avatar embedding for runtime gallery skipped for %s: %s", staff.pin, e
        )

    base_dir: Optional[str] = None
    try:
        if staff.avatar and getattr(staff.avatar, "path", None):
            base_dir = os.path.dirname(staff.avatar.path)
    except Exception:
        base_dir = None

    if base_dir:
        gr_path = os.path.join(base_dir, f"{staff.pin}_gallery_real.npy")
        if os.path.isfile(gr_path):
            try:
                e = np.load(gr_path)
                if e.ndim == 1:
                    e = e.reshape(1, -1)
                if e.size > 0:
                    rows.append(e.astype(np.float64))
                    breakdown["gallery_real_npy_prototypes"] = int(e.shape[0])
            except Exception as e:
                logger.warning("gallery_real.npy skipped for %s: %s", staff.pin, e)

    gal: Optional[np.ndarray]
    if not rows:
        gal = None
    else:
        gal = np.vstack(rows)
        gal = _l2_normalize_embedding_rows(gal)
        gal = _dedupe_normalized_rows(gal, min_cos=0.999)

    _save_staff_runtime_gallery_cache(cache_path, signature, gal, breakdown)
    _staff_runtime_gallery_mem_cache[staff.pin] = (signature, gal, dict(breakdown))
    return gal, breakdown


def build_multi_staff_runtime_gallery_matrix(
    staff_iterable: Iterable["models.Staff"],
) -> tuple[np.ndarray, list["models.Staff"]]:
    """Stack runtime verification prototypes from many staff rows for 1:N search.

    For each staff member, calls :func:`build_runtime_gallery_embeddings` (mask,
    live avatar, optional ``gallery_real.npy``). Same runtime sources as verify.

    Returns:
        ``G`` with shape ``(n_prototypes, dim)`` (rows L2-normalized) and
        ``owners[i]`` = staff owning prototype row ``i``.

    Raises:
        ValueError: If no prototypes exist for any staff in the iterable.
    """
    global _multi_staff_runtime_gallery_mem_cache

    staff_list = list(staff_iterable)
    staff_pins = tuple(staff.pin for staff in staff_list)

    mem_cached = _multi_staff_runtime_gallery_mem_cache
    if mem_cached and mem_cached[0] == staff_pins:
        owners_by_pin = {staff.pin: staff for staff in staff_list}
        owners = [owners_by_pin[pin] for pin in mem_cached[2] if pin in owners_by_pin]
        if owners and len(owners) == int(mem_cached[1].shape[0]):
            return mem_cached[1], owners

    cache_path = _multi_staff_runtime_gallery_cache_path()
    disk_cached = _load_multi_staff_runtime_gallery_cache(cache_path, staff_list)
    if disk_cached is not None:
        matrix, owners = disk_cached
        _multi_staff_runtime_gallery_mem_cache = (
            staff_pins,
            matrix,
            tuple(owner.pin for owner in owners),
        )
        return matrix, owners

    owners: list[models.Staff] = []
    owner_pins: list[str] = []
    blocks: list[np.ndarray] = []
    for staff in staff_list:
        gal, _bd = build_runtime_gallery_embeddings(staff)
        if gal is None or gal.size == 0:
            continue
        for i in range(int(gal.shape[0])):
            owners.append(staff)
            owner_pins.append(staff.pin)
            blocks.append(gal[i : i + 1])
    if not blocks:
        raise ValueError("No runtime gallery prototypes for any staff member.")
    matrix = np.vstack(blocks)
    _save_multi_staff_runtime_gallery_cache(
        cache_path,
        staff_pins,
        matrix,
        tuple(owner_pins),
    )
    _multi_staff_runtime_gallery_mem_cache = (
        staff_pins,
        matrix,
        tuple(owner_pins),
    )
    return matrix, owners


def verify_staff_face_embedding_score(
    staff: "models.Staff", probe_embedding: np.ndarray
) -> tuple[bool, float, dict[str, Any]]:
    """
    Compare probe ArcFace embedding to multi-prototype **runtime** gallery.

    Score: blend of max cosine and mean(top-k). Threshold from
    ``FACE_VERIFY_THRESHOLD_VERIFIED`` (decoupled from per-staff .pt files).
    """
    gal, gallery_breakdown = build_runtime_gallery_embeddings(staff)
    if gal is None or gal.size == 0:
        raise ValueError("No gallery embeddings available for this staff member.")

    p = _l2_normalize_embedding_rows(
        np.asarray(probe_embedding, dtype=np.float64).reshape(1, -1)
    )
    sims = (gal @ p.T).ravel()
    max_sim = float(np.max(sims))
    n = int(gal.shape[0])
    if n >= 3:
        top3 = np.partition(sims, -3)[-3:]
        score = float(0.55 * max_sim + 0.45 * float(np.mean(top3)))
    elif n == 2:
        top2 = np.partition(sims, -2)[-2:]
        score = float(0.6 * max_sim + 0.4 * float(np.mean(top2)))
    else:
        score = max_sim

    thr = float(getattr(settings, "FACE_VERIFY_THRESHOLD_VERIFIED", 0.76))
    thr_review = float(getattr(settings, "FACE_VERIFY_THRESHOLD_REVIEW", 0.68))
    meta: dict[str, Any] = {
        "gallery_templates": n,
        "gallery_breakdown": dict(gallery_breakdown),
        "threshold_used": thr,
        "threshold_review": thr_review,
        "max_cosine": max_sim,
    }
    verified = score >= thr
    return verified, score, meta


def _classify_runtime_gallery_matches(
    faces: list,
    embeddings_normalized: np.ndarray,
    staff_embeddings_normalized: np.ndarray,
    row_owners: list["models.Staff"],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Run k-NN search against a prepared runtime gallery matrix.

    Args:
        faces: Detected face objects from ArcFace.
        embeddings_normalized: Probe embeddings with shape ``(n, dim)``.
        staff_embeddings_normalized: Gallery prototype matrix.
        row_owners: Owner row for each gallery prototype.

    Returns:
        Recognized staff rows and unknown face rows.
    """
    n_proto = int(staff_embeddings_normalized.shape[0])
    k_nn = min(3, n_proto)
    nbrs = NearestNeighbors(n_neighbors=k_nn, metric="cosine").fit(
        staff_embeddings_normalized
    )
    distances, indices = nbrs.kneighbors(embeddings_normalized)

    thr_main = float(getattr(settings, "FACE_RECOGNITION_THRESHOLD", 0.76))
    thr_relax = float(getattr(settings, "FACE_RECOGNITION_THRESHOLD_RELAXED", 0.70))
    gap_min = float(getattr(settings, "FACE_RECOGNITION_MIN_NEIGHBOR_GAP", 0.085))

    recognized_staff: list[dict[str, Any]] = []
    unknown_faces: list[dict[str, Any]] = []

    for idx, face in enumerate(faces):
        bbox = face.bbox.astype(int).tolist()
        dist_row = distances[idx]
        idx_row = indices[idx]
        similarity = float(1.0 - dist_row[0])
        best_proto_i = int(idx_row[0])
        staff_best = row_owners[best_proto_i]
        if k_nn >= 2:
            second_proto_i = int(idx_row[1])
            sim_second = float(1.0 - dist_row[1])
            if row_owners[second_proto_i].pk == staff_best.pk:
                gap = 1.0
            else:
                gap = similarity - sim_second
        else:
            gap = 1.0

        accept = similarity >= thr_main or (similarity >= thr_relax and gap >= gap_min)

        if accept:
            recognized_staff.append(
                {
                    "pin": staff_best.pin,
                    "name": staff_best.name,
                    "surname": staff_best.surname,
                    "department": (
                        staff_best.department.name if staff_best.department else None
                    ),
                    "similarity": similarity,
                    "bbox": bbox,
                }
            )
        else:
            unknown_faces.append({"status": "unknown", "bbox": bbox})

    return recognized_staff, unknown_faces


# -----------------------------------
# 5. Negative Sample Generation
# -----------------------------------


def generate_negative_samples(staff, neighbors_count=7):
    """
    Generates negative samples for training the face recognition model.

    Args:
        staff (Staff): Staff object.
        neighbors_count (int): Number of negative samples to generate.

    Returns:
        list: List of negative embeddings.
    """
    logger.info(f"Generating negative samples for {staff.pin}")

    staff_list = list(
        models.Staff.objects.filter(avatar__isnull=False).exclude(id=staff.id)
    )
    negative_embeddings = []

    for neighbor in staff_list:
        try:
            embeddings_path = os.path.join(
                os.path.dirname(neighbor.avatar.path), f"{neighbor.pin}_embeddings.npy"
            )
            if os.path.exists(embeddings_path):
                embeddings = np.load(embeddings_path)
                negative_embeddings.extend(embeddings)
            else:
                image_path = neighbor.avatar.path
                if not os.path.exists(image_path):
                    continue

                image = imread_bgr(image_path)
                if image is None:
                    logger.error(f"Failed to load image: {image_path}")
                    continue

                image = preprocess_image(image)

                encoding = create_face_encoding(image)
                if encoding is not None:
                    negative_embeddings.append(encoding)

        except Exception as e:
            logger.warning(
                f"Failed to create encoding for negative sample from {neighbor.pin}: {e}",
            )

        if len(negative_embeddings) >= neighbors_count:
            break

    return negative_embeddings[:neighbors_count]


# -----------------------------------
# 6. Face Recognition Models
# -----------------------------------


class GeneralFaceRecognitionModel(nn.Module):
    """
    General face recognition model using MLP for all staff members.

    Args:
        num_classes (int): Number of classes (staff members).
    """

    def __init__(self, num_classes):
        super(GeneralFaceRecognitionModel, self).__init__()
        self.fc1 = nn.Linear(512, 512)
        self.bn1 = nn.BatchNorm1d(512)
        self.dropout1 = nn.Dropout(0.5)
        self.fc2 = nn.Linear(512, 256)
        self.bn2 = nn.BatchNorm1d(256)
        self.dropout2 = nn.Dropout(0.5)
        self.fc3 = nn.Linear(256, num_classes)

    def forward(self, x):
        x = torch.relu(self.bn1(self.fc1(x)))
        x = self.dropout1(x)
        x = torch.relu(self.bn2(self.fc2(x)))
        x = self.dropout2(x)
        return self.fc3(x)


class FaceRecognitionResNet(nn.Module):
    """
    Individual face recognition model using MLP.
    """

    def __init__(self):
        super().__init__()
        self.fc1 = nn.Linear(512, 512)
        self.bn1 = nn.BatchNorm1d(512)
        self.dropout1 = nn.Dropout(0.5)
        self.fc2 = nn.Linear(512, 256)
        self.bn2 = nn.BatchNorm1d(256)
        self.dropout2 = nn.Dropout(0.5)
        self.fc3 = nn.Linear(256, 128)
        self.bn3 = nn.BatchNorm1d(128)
        self.dropout3 = nn.Dropout(0.5)
        self.fc4 = nn.Linear(128, 1)

    def forward(self, x):
        x = torch.relu(self.bn1(self.fc1(x)))
        x = self.dropout1(x)
        x = torch.relu(self.bn2(self.fc2(x)))
        x = self.dropout2(x)
        x = torch.relu(self.bn3(self.fc3(x)))
        x = self.dropout3(x)
        return self.fc4(x)


# -----------------------------------
# 7. Evaluation Metrics
# -----------------------------------


def evaluate_metrics(y_true, y_pred):
    """
    Computes Precision, Recall, and F1-score.

    Args:
        y_true (list or np.ndarray): True labels.
        y_pred (list or np.ndarray): Predicted labels.

    Returns:
        tuple: Precision, Recall, F1-score.
    """
    zero_division_safe = cast(Any, 0)
    precision = precision_score(
        y_true, y_pred, average="weighted", zero_division=zero_division_safe
    )
    recall = recall_score(
        y_true, y_pred, average="weighted", zero_division=zero_division_safe
    )
    f1 = f1_score(y_true, y_pred, average="weighted", zero_division=zero_division_safe)
    return precision, recall, f1


# -----------------------------------
# 8. Class Weights and Sampler
# -----------------------------------


def get_class_weights(labels, class_weights):
    """
    Assigns weight to each sample based on its class.

    Args:
        labels (list or np.ndarray): List of class labels (integers).
        class_weights (np.ndarray): Array of class weights corresponding to each class.

    Returns:
        WeightedRandomSampler: Sampler for balancing classes.
    """
    samples_weights = class_weights[labels]
    samples_weights_tensor = torch.from_numpy(samples_weights).double()
    sampler = WeightedRandomSampler(
        samples_weights_tensor.tolist(),
        num_samples=len(samples_weights_tensor),
        replacement=True,
    )
    return sampler


# -----------------------------------
# 9. Model Saving and Loading
# -----------------------------------


def save_model_for_staff(model, staff, model_path_suffix="model.pt"):
    """
    Saves the trained model for a staff member.

    Args:
        model (nn.Module): Trained model.
        staff (Staff): Staff object.
        model_path_suffix (str): Suffix for the model file name.

    Raises:
        Exception: If saving fails.
    """

    try:
        model_path = os.path.join(
            os.path.dirname(staff.avatar.path), f"{staff.pin}_{model_path_suffix}"
        )
        torch.save(model.state_dict(), model_path)
        logger.info(f"Model for {staff.pin} saved at {model_path}")

    except Exception as e:
        logger.error(f"Error saving model for {staff.pin}: {str(e)}")
        raise e


def load_model_for_staff(staff, model_path_suffix="model.pt"):
    """
    Loads the trained model for a staff member.

    Args:
        staff (Staff): Staff object.
        model_path_suffix (str): Suffix for the model file name.

    Returns:
        nn.Module: Loaded model.

    Raises:
        ValueError: If the model file does not exist.
    """

    model_path = os.path.join(
        os.path.dirname(staff.avatar.path), f"{staff.pin}_{model_path_suffix}"
    )
    if not os.path.exists(model_path):
        logger.error(f"Модель для {staff.pin} не найдена")
        raise ValueError(f"Модель для {staff.pin} не найдена")

    device = get_device()
    model = FaceRecognitionResNet().to(device)
    model.load_state_dict(
        torch.load(model_path, map_location=device, weights_only=True)
    )
    model.to(device)
    model.eval()
    logger.info(f"Model for {staff.pin} loaded from {model_path}")
    return model


def load_general_model():
    """
    Loads the trained general face recognition model.

    Returns:
        nn.Module: Loaded general model.

    Raises:
        ValueError: If the general model file does not exist.
    """

    model_path = os.path.join(
        settings.GENERAL_MODELS_ROOT, "general_face_recognition_model.pt"
    )
    if not os.path.exists(model_path):
        logger.error("Общая модель не найдена")
        raise ValueError("Общая модель не найдена")

    device = get_device()
    num_classes = len(models.Staff.objects.filter(avatar__isnull=False))
    model = GeneralFaceRecognitionModel(num_classes=num_classes).to(device)
    model.load_state_dict(
        torch.load(model_path, map_location=device, weights_only=True)
    )
    model.to(device)
    model.eval()
    logger.info(f"General model loaded from {model_path}")
    return model


# -----------------------------------
# 10. Model Training Functions
# -----------------------------------


def train_face_recognition_model(staff, epochs=20, batch_size=256, learning_rate=1e-4):
    """
    Trains an individual face recognition model for the given staff member.

    Args:
        staff (Staff): Staff object.
        epochs (int): Number of training epochs.
        batch_size (int): Batch size.
        learning_rate (float): Learning rate.

    Returns:
        FaceRecognitionResNet: Trained model.
    """
    logger.info("Начало обучения индивидуальной модели.")

    device = get_device()

    if not staff.avatar or not os.path.exists(staff.avatar.path):
        logger.error(f"Avatar отсутствует для {staff.pin}")
        raise ValueError(f"Avatar отсутствует для {staff.pin}")

    embeddings_path = os.path.join(
        os.path.dirname(staff.avatar.path), f"{staff.pin}_embeddings.npy"
    )
    if not os.path.exists(embeddings_path):
        logger.info(f"Эмбеддинги не найдены для {staff.pin}, создаем их.")
        create_embeddings_for_staff(staff)

    if not os.path.exists(embeddings_path):
        logger.error(f"Эмбеддинги для {staff.pin} не найдены по пути {embeddings_path}")
        raise ValueError(
            f"Эмбеддинги для {staff.pin} не найдены по пути {embeddings_path}"
        )

    positive_embeddings = np.load(embeddings_path)
    if positive_embeddings.size == 0:
        logger.error(f"Эмбеддинги пусты для {staff.pin}")
        raise ValueError(f"Эмбеддинги пусты для {staff.pin}")

    positive_embeddings = torch.tensor(positive_embeddings, dtype=torch.float32).to(
        device
    )

    negative_embeddings = generate_negative_samples(staff)

    if positive_embeddings.size(0) == 0 or len(negative_embeddings) == 0:
        logger.error(f"Недостаточно данных для обучения модели для {staff.pin}.")
        raise ValueError(f"Недостаточно данных для обучения модели для {staff.pin}.")

    neg_np = np.asarray(negative_embeddings, dtype=np.float32)
    if neg_np.ndim == 1:
        neg_np = neg_np.reshape(1, -1)
    negative_embeddings = torch.tensor(neg_np, dtype=torch.float32).to(device)

    embeddings_combined = torch.cat([positive_embeddings, negative_embeddings], dim=0)
    labels = torch.tensor(
        [1] * positive_embeddings.size(0) + [0] * negative_embeddings.size(0),
        dtype=torch.float32,
    ).to(device)

    labels_np = labels.cpu().numpy()
    labels_int = labels_np.astype(int)

    classes = np.unique(labels_np)
    if len(classes) < 2:
        logger.warning(f"Only one class found for {staff.pin}. Adjusting classes.")
        classes = np.append(classes, 1 - classes[0])

    class_weights = 1.0 / np.array([np.sum(labels_np == c) for c in classes])

    sampler = get_class_weights(labels_int, class_weights)

    dataset = TensorDataset(embeddings_combined, labels)
    train_loader = DataLoader(
        dataset, batch_size=batch_size, sampler=sampler, num_workers=0
    )

    y_split = labels.cpu().numpy()
    strat = _sklearn_stratify_y(y_split)
    try:
        _, inputs_val_np, _, labels_val_np = train_test_split(
            embeddings_combined.cpu().numpy(),
            y_split,
            test_size=0.2,
            random_state=42,
            stratify=strat,
        )
    except ValueError:
        _, inputs_val_np, _, labels_val_np = train_test_split(
            embeddings_combined.cpu().numpy(),
            y_split,
            test_size=0.2,
            random_state=42,
            stratify=None,
        )

    inputs_val = torch.tensor(inputs_val_np, dtype=torch.float32).to(device)
    labels_val = torch.tensor(labels_val_np, dtype=torch.float32).to(device)

    val_dataset = TensorDataset(inputs_val, labels_val)
    val_loader = DataLoader(
        val_dataset, batch_size=batch_size, shuffle=False, num_workers=0
    )

    model = FaceRecognitionResNet().to(device)

    criterion = nn.BCEWithLogitsLoss()
    optimizer = AdamW(model.parameters(), lr=learning_rate, weight_decay=2e-4)
    use_amp = device.type == "cuda"
    scaler = torch.GradScaler("cuda", enabled=use_amp)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="max", factor=0.5, patience=2, min_lr=1e-6
    )

    best_f1 = -1.0
    patience_es = 6
    trigger_times = 0
    min_epochs_before_es = 4
    best_model_path = os.path.join(
        os.path.dirname(staff.avatar.path), f"{staff.pin}_best_model.pt"
    )
    os.makedirs(os.path.dirname(best_model_path), exist_ok=True)

    for epoch in range(epochs):
        model.train()
        train_loss = 0.0
        all_preds = []
        all_labels_list = []

        for batch_inputs, batch_labels in train_loader:
            batch_inputs = batch_inputs.to(device)
            batch_labels = batch_labels.to(device)

            optimizer.zero_grad()
            if use_amp:
                with torch.autocast("cuda"):
                    outputs = model(batch_inputs).squeeze()
                    loss = criterion(outputs, batch_labels)
                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
            else:
                outputs = model(batch_inputs).squeeze()
                loss = criterion(outputs, batch_labels)
                loss.backward()

            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)

            if use_amp:
                scaler.step(optimizer)
                scaler.update()
            else:
                optimizer.step()

            train_loss += loss.item()

            preds = torch.sigmoid(outputs) >= 0.5
            all_preds.extend(preds.cpu().numpy())
            all_labels_list.extend(batch_labels.cpu().numpy())

        train_accuracy = np.mean(np.array(all_preds) == np.array(all_labels_list))
        train_precision, train_recall, train_f1 = evaluate_metrics(
            all_labels_list, all_preds
        )
        logger.info(
            f"Epoch {epoch+1}, Train Loss: {train_loss / len(train_loader):.4f}, "
            f"Train Acc: {train_accuracy:.4f}, Precision: {train_precision:.4f}, "
            f"Recall: {train_recall:.4f}, F1: {train_f1:.4f}"
        )

        model.eval()
        val_loss = 0.0
        val_preds = []
        val_true = []

        with torch.no_grad():
            for batch_inputs, batch_labels in val_loader:
                batch_inputs = batch_inputs.to(device)
                batch_labels = batch_labels.to(device)

                outputs = model(batch_inputs).squeeze()
                loss = criterion(outputs, batch_labels)
                val_loss += loss.item()

                preds = torch.sigmoid(outputs) >= 0.5
                val_preds.extend(preds.cpu().numpy())
                val_true.extend(batch_labels.cpu().numpy())

        val_accuracy = np.mean(np.array(val_preds) == np.array(val_true))
        val_precision, val_recall, val_f1 = evaluate_metrics(val_true, val_preds)
        scheduler.step(val_f1)
        gap = train_f1 - val_f1
        logger.info(
            f"Epoch {epoch+1}, Validation Loss: {val_loss / len(val_loader):.4f}, "
            f"Val Acc: {val_accuracy:.4f}, Precision: {val_precision:.4f}, "
            f"Recall: {val_recall:.4f}, F1: {val_f1:.4f}, "
            f"train-val F1 gap: {gap:.4f}"
        )

        if val_f1 > best_f1 + 1e-6:
            best_f1 = val_f1
            trigger_times = 0
            torch.save(model.state_dict(), best_model_path)
            logger.info(f"Best model updated and saved at {best_model_path}")
        else:
            trigger_times += 1
            if epoch + 1 >= min_epochs_before_es and trigger_times >= patience_es:
                logger.info("Early stopping triggered.")
                break

    final_model_path = os.path.join(
        os.path.dirname(staff.avatar.path), f"{staff.pin}_model.pt"
    )
    os.makedirs(os.path.dirname(final_model_path), exist_ok=True)
    if os.path.isfile(best_model_path):
        model.load_state_dict(
            torch.load(best_model_path, map_location=device, weights_only=True)
        )
        logger.info("Final export uses best validation weights for %s.", staff.pin)
    torch.save(model.state_dict(), final_model_path)
    logger.info(f"Model for {staff.pin} saved at {final_model_path}")

    return model


def train_general_model(epochs=100, batch_size=256, learning_rate=1e-4):
    """
    Общая модель по эмбеддингам всех сотрудников с аватаром (вся база, не один отдел).

    Каждый запуск подмешивает все найденные `{pin}_embeddings.npy`. При наличии чекпоинта и
    `general_face_model_meta.json` возможен warm start или расширение последнего слоя при новых сотрудниках.
    """
    logger.info("Начало обучения общей модели.")

    device = get_device()

    staff_members = list(
        models.Staff.objects.filter(avatar__isnull=False).order_by("pk").distinct()
    )
    num_staff = len(staff_members)
    ordered_pins = [s.pin for s in staff_members]
    logger.info(
        "Общая модель: классы в фиксированном порядке по pk (%s слотов); в обучение попадут "
        "только те, у кого на диске есть %s_embeddings.npy.",
        num_staff,
        "{pin}",
    )
    logger.info(f"Number of staff members (avatar__isnull=False): {num_staff}")

    if num_staff == 0:
        logger.error("No staff members found with avatars for training.")
        raise ValueError("No staff members found with avatars for training.")

    all_embeddings = []
    all_labels = []
    staff_pin_to_label = {staff.pin: idx for idx, staff in enumerate(staff_members)}

    for staff in staff_members:
        if (
            not staff.avatar
            or not staff.avatar.path
            or not os.path.exists(staff.avatar.path)
        ):
            logger.warning(
                f"Staff {staff.pin} has no associated avatar file. Skipping."
            )
            continue

        embeddings_path = os.path.join(
            os.path.dirname(staff.avatar.path), f"{staff.pin}_embeddings.npy"
        )
        if not os.path.exists(embeddings_path):
            logger.warning(
                f"Embeddings for {staff.pin} not found at {embeddings_path}. Skipping."
            )
            continue

        embeddings = np.load(embeddings_path)
        if embeddings.size == 0:
            logger.warning(f"Embeddings for {staff.pin} are empty. Skipping.")
            continue

        labels = [staff_pin_to_label[staff.pin]] * len(embeddings)
        all_embeddings.extend(embeddings)
        all_labels.extend(labels)

    all_embeddings = np.array(all_embeddings)
    all_labels = np.array(all_labels)

    label_counts = Counter(all_labels)
    logger.info(f"Label counts before filtering: {label_counts}")

    valid_labels = [label for label, count in label_counts.items() if count >= 2]
    logger.info(f"Valid labels (>=2 samples): {valid_labels}")

    if not valid_labels:
        logger.error("No classes with at least two samples available for training.")
        raise ValueError("Insufficient data: No classes with at least two samples.")

    mask = np.isin(all_labels, valid_labels)
    all_embeddings = all_embeddings[mask]
    all_labels = all_labels[mask]

    excluded_labels = set(range(num_staff)) - set(valid_labels)
    if excluded_labels:
        logger.warning(f"Excluded classes with insufficient samples: {excluded_labels}")

    num_classes = len(staff_pin_to_label)
    logger.info(f"Number of classes after filtering: {num_classes}")

    if not all_embeddings.any():
        logger.error("Insufficient data to train the general model after filtering.")
        raise ValueError(
            "Insufficient data to train the general model after filtering."
        )

    all_embeddings = torch.tensor(all_embeddings, dtype=torch.float32).to(device)
    all_labels = torch.tensor(all_labels, dtype=torch.long).to(device)

    if torch.any(all_labels >= num_classes) or torch.any(all_labels < 0):
        invalid_labels = all_labels[(all_labels >= num_classes) | (all_labels < 0)]
        logger.error(f"Invalid labels found: {invalid_labels}")
        raise ValueError("Found labels outside the valid range.")

    logger.info("All labels are within the valid range.")

    unique_y = np.unique(all_labels.cpu().numpy())

    class_weights_present = compute_class_weight(
        class_weight="balanced",
        classes=unique_y,
        y=all_labels.cpu().numpy(),
    )

    class_weights = np.ones(num_classes, dtype=np.float32)

    class_weights[unique_y] = class_weights_present

    class_weights = torch.tensor(class_weights, dtype=torch.float32).to(device)
    criterion = nn.CrossEntropyLoss(weight=class_weights, label_smoothing=0.05)

    y_split = all_labels.cpu().numpy()
    strat = _sklearn_stratify_y(y_split)
    try:
        inputs_train, inputs_val, labels_train, labels_val = train_test_split(
            all_embeddings.cpu().numpy(),
            y_split,
            test_size=0.2,
            random_state=42,
            stratify=strat,
        )
    except ValueError:
        inputs_train, inputs_val, labels_train, labels_val = train_test_split(
            all_embeddings.cpu().numpy(),
            y_split,
            test_size=0.2,
            random_state=42,
            stratify=None,
        )

    inputs_train = torch.tensor(inputs_train, dtype=torch.float32).to(device)
    inputs_val = torch.tensor(inputs_val, dtype=torch.float32).to(device)
    labels_train = torch.tensor(labels_train, dtype=torch.long).to(device)
    labels_val = torch.tensor(labels_val, dtype=torch.long).to(device)

    labels_train_np = labels_train.cpu().numpy()
    labels_train_int = labels_train_np.astype(int)

    sampler = get_class_weights(labels_train_int, class_weights.cpu().numpy())

    train_dataset = TensorDataset(inputs_train, labels_train)
    val_dataset = TensorDataset(inputs_val, labels_val)

    train_loader = DataLoader(
        train_dataset, batch_size=batch_size, sampler=sampler, num_workers=0
    )
    val_loader = DataLoader(
        val_dataset, batch_size=batch_size, shuffle=False, num_workers=0
    )

    final_model_path = os.path.join(
        settings.GENERAL_MODELS_ROOT, "general_face_recognition_model.pt"
    )
    meta_path = _general_model_meta_path()
    os.makedirs(settings.GENERAL_MODELS_ROOT, exist_ok=True)

    model = GeneralFaceRecognitionModel(num_classes=num_staff).to(device)
    warm_lr = float(learning_rate)
    if os.path.isfile(final_model_path):
        try:
            ckpt = torch.load(final_model_path, map_location=device, weights_only=True)
            old_nc = int(ckpt["fc3.weight"].shape[0])
            meta_pins: list[str] = []
            if os.path.isfile(meta_path):
                with open(meta_path, encoding="utf-8") as mf:
                    meta_pins = list(json.load(mf).get("pins") or [])

            if old_nc == num_staff:
                model.load_state_dict(ckpt, strict=True)
                warm_lr = float(learning_rate) * 0.25
                logger.info(
                    "Общая модель: warm start, классов %s (как в прошлом чекпоинте), lr=%s",
                    old_nc,
                    warm_lr,
                )
            elif (
                old_nc < num_staff
                and len(meta_pins) == old_nc
                and ordered_pins[:old_nc] == meta_pins
            ):
                _apply_general_checkpoint_partial(model, ckpt, old_nc, num_staff)
                warm_lr = float(learning_rate) * 0.35
                logger.info(
                    "Общая модель: расширение с %s до %s классов (префикс pin-ов совпал с meta)",
                    old_nc,
                    num_staff,
                )
            elif old_nc != num_staff:
                logger.warning(
                    "Чекпоинт: %s классов, сейчас в базе %s слотов; meta/prefix не совпали — "
                    "обучение с нуля. После успешного прогона сохранится general_face_model_meta.json.",
                    old_nc,
                    num_staff,
                )
        except Exception as exc:
            logger.warning("Warm start общей модели пропущен: %s", exc)

    optimizer = AdamW(model.parameters(), lr=warm_lr, weight_decay=2e-4)
    use_amp = device.type == "cuda"
    scaler = torch.GradScaler("cuda", enabled=use_amp)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="max", factor=0.5, patience=3, min_lr=1e-6
    )

    best_f1 = -1.0
    patience_es = 7
    trigger_times = 0
    min_epochs_before_es = 5
    best_model_path = os.path.join(
        settings.GENERAL_MODELS_ROOT, "best_general_face_recognition_model.pt"
    )
    os.makedirs(os.path.dirname(best_model_path), exist_ok=True)

    for epoch in range(epochs):
        model.train()
        train_loss = 0.0
        all_preds = []
        all_labels_list = []

        for batch_inputs, batch_labels in train_loader:
            batch_inputs = batch_inputs.to(device)
            batch_labels = batch_labels.to(device)

            optimizer.zero_grad()
            if use_amp:
                with torch.autocast("cuda"):
                    outputs = model(batch_inputs)
                    loss = criterion(outputs, batch_labels)
                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
            else:
                outputs = model(batch_inputs)
                loss = criterion(outputs, batch_labels)
                loss.backward()

            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)

            if use_amp:
                scaler.step(optimizer)
                scaler.update()
            else:
                optimizer.step()

            train_loss += loss.item()

            preds = torch.argmax(outputs, dim=1)
            all_preds.extend(preds.cpu().numpy())
            all_labels_list.extend(batch_labels.cpu().numpy())

        train_accuracy = np.mean(np.array(all_preds) == np.array(all_labels_list))
        train_precision, train_recall, train_f1 = evaluate_metrics(
            all_labels_list, all_preds
        )
        logger.info(
            f"Epoch {epoch+1}, Train Loss: {train_loss / len(train_loader):.4f}, "
            f"Train Acc: {train_accuracy:.4f}, Precision: {train_precision:.4f}, "
            f"Recall: {train_recall:.4f}, F1: {train_f1:.4f}"
        )

        model.eval()
        val_loss = 0.0
        val_preds = []
        val_true = []

        with torch.no_grad():
            for batch_inputs, batch_labels in val_loader:
                batch_inputs = batch_inputs.to(device)
                batch_labels = batch_labels.to(device)

                outputs = model(batch_inputs)
                loss = criterion(outputs, batch_labels)
                val_loss += loss.item()

                preds = torch.argmax(outputs, dim=1)
                val_preds.extend(preds.cpu().numpy())
                val_true.extend(batch_labels.cpu().numpy())

        val_accuracy = np.mean(np.array(val_preds) == np.array(val_true))
        val_precision, val_recall, val_f1 = evaluate_metrics(val_true, val_preds)
        scheduler.step(val_f1)
        gap = train_f1 - val_f1
        logger.info(
            f"Epoch {epoch+1}, Validation Loss: {val_loss / len(val_loader):.4f}, "
            f"Val Acc: {val_accuracy:.4f}, Precision: {val_precision:.4f}, "
            f"Recall: {val_recall:.4f}, F1: {val_f1:.4f}, "
            f"train-val F1 gap: {gap:.4f}"
        )

        if val_f1 > best_f1 + 1e-6:
            best_f1 = val_f1
            trigger_times = 0
            torch.save(model.state_dict(), best_model_path)
            logger.info(f"Best model updated and saved at {best_model_path}")
        else:
            trigger_times += 1
            if epoch + 1 >= min_epochs_before_es and trigger_times >= patience_es:
                logger.info("Early stopping triggered.")
                break

    if os.path.isfile(best_model_path):
        model.load_state_dict(
            torch.load(best_model_path, map_location=device, weights_only=True)
        )
        logger.info("General model export uses best validation checkpoint.")
    torch.save(model.state_dict(), final_model_path)
    logger.info(f"General model saved at {final_model_path}")
    try:
        with open(_general_model_meta_path(), "w", encoding="utf-8") as mf:
            json.dump(
                {"pins": ordered_pins, "num_classes": num_staff},
                mf,
                ensure_ascii=False,
                indent=2,
            )
        logger.info("Saved class order to general_face_model_meta.json")
    except OSError as exc:
        logger.warning("Could not save general_face_model_meta.json: %s", exc)


# -----------------------------------
# 11. Face Recognition Function
# -----------------------------------


def recognize_faces_in_image(image_file):
    """Recognize staff faces using the same **runtime gallery** rules as verify.

    Builds a joint matrix of all per-staff prototypes from
    :func:`build_runtime_gallery_embeddings` (mask, avatar, ``gallery_real.npy``,
    optional legacy full ``embeddings.npy`` if enabled), then k-NN per detected
    face. Thresholds remain ``FACE_RECOGNITION_THRESHOLD*`` (1:N gallery search),
    not ``FACE_VERIFY_*`` (1:1 verify).

    Args:
        image_file (InMemoryUploadedFile): Uploaded image file.

    Returns:
        tuple: (recognized_staff, unknown_faces)

    Raises:
        ValidationError: If recognition fails.
    """
    try:
        load_arcface_model()
        img = load_image_from_memory(image_file)
        faces = _arcface_get_faces(img)

        if not faces:
            logger.warning("Лица не найдены на изображении")
            raise ValidationError("Лица не найдены на изображении")

        try:
            face_rows = [_probe_embedding_row(f.embedding) for f in faces]
        except ValueError as e:
            raise ValidationError(str(e)) from e
        dim_face = int(face_rows[0].shape[0])
        for row in face_rows:
            if row.shape[0] != dim_face:
                raise ValidationError(
                    "Несовпадение размерности векторов лиц на снимке — проверьте файл."
                )
        embeddings = np.stack(face_rows, axis=0)
        embeddings_normalized = _l2_normalize_embedding_rows(embeddings)

        staff_qs = list(
            models.Staff.objects.filter(
                Q(face_mask__isnull=False) | (Q(avatar__isnull=False) & ~Q(avatar=""))
            )
            .select_related("department", "face_mask")
            .order_by("pin")
        )
        if not staff_qs:
            raise ValidationError(
                "В базе нет сотрудников с аватаром или сохранённой маской лица."
            )

        def ensure_dim_matches(matrix: np.ndarray) -> None:
            dim_staff = int(matrix.shape[1])
            if dim_staff != dim_face:
                raise ValidationError(
                    f"Размерность эталонов в базе ({dim_staff}) не совпадает с моделью "
                    f"распознавания ({dim_face})."
                )

        recognized_staff: list[dict[str, Any]] = []
        unknown_faces: list[dict[str, Any]] = []

        try:
            cached_matrix, cached_owners = build_cached_staff_runtime_gallery_matrix(
                staff_qs
            )
        except ValueError:
            cached_matrix = None
            cached_owners = []
        if cached_matrix is not None:
            ensure_dim_matches(cached_matrix)
            recognized_staff, unknown_faces = _classify_runtime_gallery_matches(
                faces,
                embeddings_normalized,
                cached_matrix,
                cached_owners,
            )
            if recognized_staff:
                logger.info(
                    "Recognition completed from cached runtime subset. Recognized: %s, Unknown: %s",
                    len(recognized_staff),
                    len(unknown_faces),
                )
                return recognized_staff, unknown_faces

        try:
            staff_embeddings_normalized, row_owners = (
                build_multi_staff_runtime_gallery_matrix(staff_qs)
            )
        except ValueError:
            raise ValidationError(
                "Нет ни одного эталона для распознавания (маска, аватар или "
                "gallery_real.npy). При необходимости выполните: "
                "python manage.py build_staff_gallery_real"
            ) from None

        ensure_dim_matches(staff_embeddings_normalized)
        recognized_staff, unknown_faces = _classify_runtime_gallery_matches(
            faces,
            embeddings_normalized,
            staff_embeddings_normalized,
            row_owners,
        )

        logger.info(
            "Recognition completed (runtime gallery). Recognized: %s, Unknown: %s",
            len(recognized_staff),
            len(unknown_faces),
        )
        return recognized_staff, unknown_faces

    except ValidationError:
        raise
    except Exception:
        logger.exception("Ошибка при распознавании лиц")
        raise ValidationError(
            "Не удалось выполнить распознавание. Попробуйте другой снимок."
        ) from None
