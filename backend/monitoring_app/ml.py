import importlib
import json
import logging
import os
import traceback
from collections import Counter
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


class _ArcfacePrepareCache:
    """Последний det_size для FaceAnalysis.prepare — не вызывать prepare повторно зря."""

    det_size: Optional[tuple[int, int]] = None


def _arcface_prepare_det(model: Any, ctx_id: int, det_size: tuple[int, int]) -> None:
    if _ArcfacePrepareCache.det_size == det_size:
        return
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
                FaceAnalysis = _get_face_analysis()
                cuda_available = torch.cuda.is_available()
                device_type = "GPU" if cuda_available else "CPU"
                logger.info(f"Using {device_type} for ArcFace model")
                providers = (
                    ["CUDAExecutionProvider", "CPUExecutionProvider"]
                    if cuda_available
                    else ["CPUExecutionProvider"]
                )
                model = FaceAnalysis(
                    name="buffalo_l",
                    providers=providers,
                )
                ctx_id = 0 if cuda_available else -1
                model.prepare(ctx_id=ctx_id, det_size=(640, 640))
                _ArcfacePrepareCache.det_size = (640, 640)
                arcface_model_holder.instance = model


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


def staff_has_trained_recognition_model(staff: "models.Staff") -> bool:
    """True if per-staff PyTorch head was saved after training (not used in verify yet)."""
    try:
        if not staff.avatar or not getattr(staff.avatar, "path", None):
            return False
        base = os.path.dirname(staff.avatar.path)
    except Exception:
        return False
    pin = staff.pin
    return os.path.isfile(os.path.join(base, f"{pin}_best_model.pt")) or os.path.isfile(
        os.path.join(base, f"{pin}_model.pt")
    )


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


def build_staff_gallery_embeddings(staff: "models.Staff") -> Optional[np.ndarray]:
    """
    ArcFace embedding prototypes for verification: stored mask, fresh avatar file,
    and optional {pin}_embeddings.npy (augmented gallery). Rows are L2-normalized.
    """
    rows: list[np.ndarray] = []

    try:
        fm = staff.face_mask
        if fm is not None and fm.mask_encoding:
            mm = _mask_json_to_matrix(fm.mask_encoding)
            if mm is not None:
                rows.append(mm)
    except ObjectDoesNotExist:
        pass

    try:
        if staff.avatar and getattr(staff.avatar, "path", None):
            ap = staff.avatar.path
            if ap and os.path.isfile(ap):
                enc = create_face_encoding(ap)
                if enc is not None:
                    rows.append(np.asarray(enc, dtype=np.float64).reshape(1, -1))
    except Exception as e:
        logger.warning("Avatar embedding for gallery skipped for %s: %s", staff.pin, e)

    try:
        if staff.avatar and getattr(staff.avatar, "path", None):
            ep = os.path.join(
                os.path.dirname(staff.avatar.path), f"{staff.pin}_embeddings.npy"
            )
            if os.path.isfile(ep):
                e = np.load(ep)
                if e.ndim == 1:
                    e = e.reshape(1, -1)
                if e.size > 0:
                    rows.append(e.astype(np.float64))
    except Exception as e:
        logger.warning("embeddings.npy for gallery skipped for %s: %s", staff.pin, e)

    if not rows:
        return None
    gal = np.vstack(rows)
    gal = _l2_normalize_embedding_rows(gal)
    gal = _dedupe_normalized_rows(gal, min_cos=0.999)
    return gal


def verify_staff_face_embedding_score(
    staff: "models.Staff", probe_embedding: np.ndarray
) -> tuple[bool, float, dict[str, Any]]:
    """
    Compare probe ArcFace embedding to multi-prototype gallery.

    Score: blend of max cosine and mean(top-k) so several agreeing templates help.
    Threshold: stricter if per-staff .pt model exists (assumes operator ran full train).
    """
    gal = build_staff_gallery_embeddings(staff)
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

    has_model = staff_has_trained_recognition_model(staff)
    thr = float(
        getattr(settings, "FACE_RECOGNITION_THRESHOLD", 0.76)
        if has_model
        else getattr(settings, "FACE_VERIFY_FALLBACK_THRESHOLD", 0.74)
    )
    meta: dict[str, Any] = {
        "trained_model_present": has_model,
        "gallery_templates": n,
        "threshold_used": thr,
        "max_cosine": max_sim,
        "verification_mode": (
            "embedding_gallery_strict" if has_model else "embedding_gallery_fallback"
        ),
    }
    verified = score >= thr
    relaxed = False
    accessory_relaxed = False
    if not verified and n >= 2:
        sims_sorted = np.sort(sims)
        second_best = float(sims_sorted[-2])
        margin = max_sim - second_best
        score_slack = float(getattr(settings, "FACE_VERIFY_RELAXED_SCORE_SLACK", 0.045))
        max_slack = float(getattr(settings, "FACE_VERIFY_RELAXED_MAX_SLACK", 0.028))
        margin_min = float(getattr(settings, "FACE_VERIFY_RELAXED_MARGIN_MIN", 0.042))
        thr_lo = thr - score_slack
        if score >= thr_lo and max_sim >= thr - max_slack and margin >= margin_min:
            verified = True
            relaxed = True
    if not verified and bool(getattr(settings, "FACE_VERIFY_ACCESSORY_ENABLE", True)):
        acc_max_min = float(getattr(settings, "FACE_VERIFY_ACCESSORY_MAX_MIN", 0.71))
        gap_need = float(
            getattr(settings, "FACE_VERIFY_ACCESSORY_SCORE_GAP_MIN", 0.035)
        )
        acc_margin = float(
            getattr(settings, "FACE_VERIFY_ACCESSORY_SECOND_MARGIN", 0.044)
        )
        single_max_min = float(
            getattr(settings, "FACE_VERIFY_ACCESSORY_SINGLE_MAX_MIN", 0.685)
        )
        single_score_min = float(
            getattr(settings, "FACE_VERIFY_ACCESSORY_SINGLE_SCORE_MIN", 0.655)
        )
        if n >= 2 and max_sim >= acc_max_min and score < thr:
            sims_sorted = np.sort(sims)
            second_best = float(sims_sorted[-2])
            margin2 = max_sim - second_best
            gap_ms = max_sim - score
            if gap_ms >= gap_need and margin2 >= acc_margin:
                verified = True
                relaxed = True
                accessory_relaxed = True
        elif (
            n == 1
            and max_sim >= single_max_min
            and max_sim < thr
            and score >= single_score_min
        ):
            verified = True
            relaxed = True
            accessory_relaxed = True
    meta["relaxed_match"] = relaxed
    meta["accessory_relaxed"] = accessory_relaxed
    return verified, score, meta


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
    """
    Recognizes faces in an image and identifies staff members.

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

        staff_qs = list(models.Staff.objects.filter(face_mask__isnull=False))
        if not staff_qs:
            raise ValidationError("В базе нет сотрудников с сохранённой маской лица.")

        staff_rows: list[np.ndarray] = []
        staff_members: list = []
        for staff in staff_qs:
            try:
                enc = staff.face_mask.mask_encoding
                staff_rows.append(_staff_mask_encoding_row(enc))
                staff_members.append(staff)
            except (TypeError, ValueError) as e:
                logger.warning(
                    "Пропуск сотрудника %s: неверный формат mask_encoding: %s",
                    getattr(staff, "pin", "?"),
                    e,
                )
                continue
        if not staff_rows:
            raise ValidationError(
                "Нет ни одного корректного эмбеддинга сотрудников в базе (проверьте маски лиц)."
            )
        dim_staff = int(staff_rows[0].shape[0])
        for row in staff_rows:
            if row.shape[0] != dim_staff:
                raise ValidationError(
                    "У сотрудников разная размерность векторов в масках — переобучите/пересохраните маски."
                )
        if dim_staff != dim_face:
            raise ValidationError(
                f"Размерность маски в базе ({dim_staff}) не совпадает с моделью "
                f"распознавания ({dim_face})."
            )
        staff_embeddings = np.stack(staff_rows, axis=0)
        staff_embeddings_normalized = _l2_normalize_embedding_rows(staff_embeddings)

        n_staff = len(staff_members)
        k_nn = min(3, n_staff)
        nbrs = NearestNeighbors(n_neighbors=k_nn, metric="cosine").fit(
            staff_embeddings_normalized
        )
        distances, indices = nbrs.kneighbors(embeddings_normalized)

        thr_main = float(getattr(settings, "FACE_RECOGNITION_THRESHOLD", 0.76))
        thr_relax = float(getattr(settings, "FACE_RECOGNITION_THRESHOLD_RELAXED", 0.70))
        gap_min = float(getattr(settings, "FACE_RECOGNITION_MIN_NEIGHBOR_GAP", 0.085))

        recognized_staff = []
        unknown_faces = []

        for idx, face in enumerate(faces):
            bbox = face.bbox.astype(int).tolist()
            dist_row = distances[idx]
            idx_row = indices[idx]
            similarity = float(1.0 - dist_row[0])
            best_staff_i = int(idx_row[0])
            if k_nn >= 2:
                sim_second = float(1.0 - dist_row[1])
                gap = (
                    1.0 if int(idx_row[1]) == best_staff_i else similarity - sim_second
                )
            else:
                gap = 1.0

            accept = similarity >= thr_main or (
                similarity >= thr_relax and gap >= gap_min
            )

            if accept:
                staff = staff_members[best_staff_i]
                recognized_staff.append(
                    {
                        "pin": staff.pin,
                        "name": staff.name,
                        "surname": staff.surname,
                        "department": (
                            staff.department.name if staff.department else None
                        ),
                        "similarity": similarity,
                        "bbox": bbox,
                    }
                )
            else:
                unknown_faces.append(
                    {
                        "status": "unknown",
                        "bbox": bbox,
                    }
                )

        logger.info(
            f"Recognition completed. Recognized: {len(recognized_staff)}, Unknown: {len(unknown_faces)}"
        )
        return recognized_staff, unknown_faces

    except ValidationError:
        raise
    except Exception:
        logger.exception("Ошибка при распознавании лиц")
        raise ValidationError(
            "Не удалось выполнить распознавание. Попробуйте другой снимок."
        ) from None
