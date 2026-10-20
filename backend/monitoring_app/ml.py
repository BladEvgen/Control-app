import importlib
import json
import logging
import os
from collections import Counter
from collections.abc import Iterable, Mapping
from threading import Lock
from typing import Any, Optional, cast

import numpy as np
import torch
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from rest_framework.exceptions import ValidationError

from monitoring_app import models

cv2 = cast(Any, importlib.import_module("cv2"))


def imread_bgr(path: str) -> Optional[np.ndarray]:
    """
    Чтение BGR для AdaFace. Сначала OpenCV; если не вышло — PIL (битые/усечённые JPEG).
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


logger = logging.getLogger(__name__)


_face_engine: Optional[Any] = None
face_engine_lock = Lock()
runtime_gallery_cache_lock = Lock()

RUNTIME_GALLERY_CACHE_VERSION = 10
_staff_runtime_gallery_mem_cache: dict[str, tuple[str, Optional[np.ndarray], dict[str, int]]] = {}
_multi_staff_runtime_gallery_mem_cache: Optional[
    tuple[tuple[str, ...], np.ndarray, tuple[str, ...]]
] = None


def _staff_pin(staff: "models.Staff") -> str:
    """Return runtime Staff.pin as a plain string for cache keys and file names."""
    return str(getattr(staff, "pin", ""))


FACE_EMBEDDING_MODEL = "adaface_ir101_webface12m"
FACE_DETECTOR_MODEL = "face_detection_yunet_2023mar"


def _pose_from_kps(kps: np.ndarray) -> np.ndarray:
    """``[yaw, pitch, roll]`` degrees from the 5 keypoints (eyes, nose, mouth corners).

    Linear fit against a 3D-landmark head pose on 700 attendance photos:
    yaw MAE ~2 deg, pitch ~4 deg — enough for the 40/35 deg probe gates.
    """
    left_eye, right_eye, nose, mouth_l, mouth_r = kps
    eye_mid, mouth_mid = (left_eye + right_eye) / 2, (mouth_l + mouth_r) / 2
    dx, dy = right_eye - left_eye
    roll = float(np.degrees(np.arctan2(dy, dx)))
    c, s = np.cos(np.radians(-roll)), np.sin(np.radians(-roll))
    rot = np.array([[c, -s], [s, c]])
    n, m = rot @ (nose - eye_mid), rot @ (mouth_mid - eye_mid)
    yaw = 82.0 * n[0] / max(float(np.hypot(dx, dy)), 1e-6) + 1.4
    pitch = 51.2 - 99.2 * n[1] / max(float(m[1]), 1e-6)
    return np.array([yaw, pitch, roll], dtype=np.float32)


class _FaceEngine:
    """YuNet detection (5 keypoints) + AdaFace IR101 embeddings, one ``get(img)`` call.

    Returns ``Face``-объекты (контейнер insightface) (``bbox``, ``kps``, ``det_score``,
    ``pose``, ``embedding``). AdaFace ONNX is built by ``scripts/export_adaface_onnx.sh``.
    """

    def __init__(self, providers: list[str]):
        import onnxruntime as ort

        root = settings.GENERAL_MODELS_ROOT
        self.detector = cv2.FaceDetectorYN.create(
            os.path.join(root, f"{FACE_DETECTOR_MODEL}.onnx"), "", (320, 320), 0.6, 0.3, 5000
        )
        so = ort.SessionOptions()
        so.enable_cpu_mem_arena = False
        self.session = ort.InferenceSession(
            os.path.join(root, f"{FACE_EMBEDDING_MODEL}.onnx"), so, providers=providers
        )
        self.input_name = self.session.get_inputs()[0].name

    def _detect(self, img: np.ndarray) -> np.ndarray:
        h, w = img.shape[:2]
        self.detector.setInputSize((w, h))
        _, dets = self.detector.detect(img)
        return np.empty((0, 15), np.float32) if dets is None else dets

    def detect(self, img: np.ndarray) -> np.ndarray:
        """YuNet rows ``[x, y, w, h, 5 kps, score]`` in ``img`` coordinates."""
        dets = self._detect(img)
        if len(dets):
            return dets
        scale = 640.0 / max(img.shape[:2])
        small = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        pad = max(small.shape[:2]) // 4
        for retry in (small, _gamma_bgr(small, 0.6)):
            dets = self._detect(cv2.copyMakeBorder(retry, pad, pad, pad, pad, cv2.BORDER_REPLICATE))
            if len(dets):
                dets = dets.copy()
                dets[:, :14] /= scale
                dets[:, [0, 1, *range(4, 14)]] -= pad / scale
                return dets
        return dets

    def get(self, img: np.ndarray) -> list:
        """Each face's ``embedding`` = L2(original crop) + L2(mirrored crop).

        Flip fusion is the standard AdaFace/ArcFace evaluation protocol; one batched run.
        """
        from insightface.app.common import Face
        from insightface.utils.face_align import norm_crop

        dets = self.detect(img)
        if not len(dets):
            return []
        crops = []
        for d in dets:
            crop = cv2.cvtColor(
                norm_crop(img, landmark=d[4:14].reshape(5, 2), image_size=112), cv2.COLOR_BGR2RGB
            )
            crops += [crop, crop[:, ::-1]]
        x = ((np.stack(crops).astype(np.float32) - 127.5) / 127.5).transpose(0, 3, 1, 2)
        emb = self.session.run(None, {self.input_name: np.ascontiguousarray(x)})[0]
        emb /= np.maximum(np.linalg.norm(emb, axis=1, keepdims=True), 1e-10)
        faces = []
        for i, d in enumerate(dets):
            kps = d[4:14].reshape(5, 2).astype(np.float32)
            face = Face(
                bbox=np.array([d[0], d[1], d[0] + d[2], d[1] + d[3]], dtype=np.float32),
                kps=kps,
                det_score=float(d[14]),
                embedding=emb[2 * i] + emb[2 * i + 1],
            )
            face.pose = _pose_from_kps(kps)
            faces.append(face)
        return faces


def load_face_engine() -> "_FaceEngine":
    """Load the face engine (YuNet + AdaFace) once per process."""
    global _face_engine
    if _face_engine is None:
        with face_engine_lock:
            if _face_engine is None:
                providers = (
                    ["CUDAExecutionProvider", "CPUExecutionProvider"]
                    if torch.cuda.is_available()
                    else ["CPUExecutionProvider"]
                )
                _face_engine = _FaceEngine(providers)
    return _face_engine


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
    pin = _staff_pin(staff)
    try:
        avatar = cast(Any, getattr(staff, "avatar", None))
        if avatar and getattr(avatar, "path", None):
            avatar_path = str(avatar.path)
            gallery_real_path = os.path.join(
                os.path.dirname(avatar_path), f"{pin}_gallery_real.npy"
            )
    except Exception:
        avatar_path = None
        gallery_real_path = None

    mask_updated: Optional[str] = None
    mask_present = False
    try:
        fm = cast(Any, getattr(staff, "face_mask", None))
        if fm is not None and fm.mask_encoding:
            mask_present = True
            if fm.updated_at is not None:
                mask_updated = fm.updated_at.isoformat()
    except ObjectDoesNotExist:
        mask_present = False

    face_sample_signatures: list[tuple[object, ...]] = []
    if bool(getattr(settings, "FACE_RUNTIME_INCLUDE_FACE_SAMPLES", True)):
        for row in _collect_trusted_staff_face_sample_records_for_staff(staff):
            p = str(row.get("path") or "")
            face_sample_signatures.append(
                (
                    row.get("id"),
                    row.get("angle"),
                    row.get("with_glasses"),
                    row.get("probe_eyeglasses_likely"),
                    row.get("updated_at"),
                    _runtime_gallery_file_signature(p),
                )
            )

    payload = {
        "pin": pin,
        "avatar": _runtime_gallery_file_signature(avatar_path),
        "gallery_real": _runtime_gallery_file_signature(gallery_real_path),
        "face_samples": face_sample_signatures,
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
        "breakdown_json": np.asarray(json.dumps(breakdown, ensure_ascii=True, sort_keys=True)),
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
    staff_by_pin = {_staff_pin(staff): staff for staff in staff_list}
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


PROBE_MAX_SIDE = 1280


def cap_long_side(image: np.ndarray, max_side: int = PROBE_MAX_SIDE) -> np.ndarray:
    long_side = max(image.shape[:2])
    if long_side <= max_side:
        return image
    scale = max_side / long_side
    return cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)


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
        return cap_long_side(image)
    except Exception as e:
        logger.error("Ошибка при чтении изображения: %s", e)
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
            logger.warning("decode_upload_image_bytes_to_bgr PIL fallback failed: %s", exc)
            raise ValidationError("Невозможно прочитать изображение.") from exc
    _staff_upload_megapixel_guard(image)
    return cap_long_side(image)


def reencode_bgr_to_canonical_jpeg_bytes(
    image_bgr: np.ndarray,
    *,
    quality: int | None = None,
) -> bytes:
    """
    Encode a BGR image as baseline JPEG — canonical on-disk format for staff uploads.
    """
    q = quality if quality is not None else int(getattr(settings, "STAFF_UPLOAD_JPEG_QUALITY", 92))
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


def _bbox_area(bbox) -> float:
    try:
        x1, y1, x2, y2 = (float(bbox[i]) for i in range(4))
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)
    except (TypeError, ValueError, IndexError):
        return 0.0


def detect_faces(image_bgr: np.ndarray) -> list:
    """Detect faces (YuNet runs at the image's own resolution, so no det_size retries)."""
    model = load_face_engine()
    if not isinstance(image_bgr, np.ndarray):
        return []
    img = preprocess_image(image_bgr)
    with face_engine_lock:
        return list(model.get(img))


def _best_face(faces: list) -> Optional[Any]:
    """Pick the main face: mostly area, with detector confidence as a tie-breaker."""
    if not faces:
        return None

    def score(face: Any) -> float:
        area = _bbox_area(getattr(face, "bbox", None))
        det = getattr(face, "det_score", None)
        if det is None:
            det_f = 0.75
        else:
            try:
                det_f = float(det)
            except (TypeError, ValueError):
                det_f = 0.75
        return area * max(0.35, min(det_f, 1.0))

    return max(faces, key=score)


def _normalized_embedding_row_from_face(face: Any) -> Optional[np.ndarray]:
    emb = getattr(face, "embedding", None)
    if emb is None:
        return None
    row = np.asarray(emb, dtype=np.float64).reshape(-1)
    norm = float(np.linalg.norm(row))
    if norm < 1e-10:
        return None
    return row / norm


def _gamma_bgr(image_bgr: np.ndarray, gamma: float) -> np.ndarray:
    x = image_bgr.astype(np.float32) / 255.0
    y = np.power(np.clip(x, 1e-6, 1.0), float(gamma))
    return np.clip(y * 255.0, 0, 255).astype(np.uint8)


def _create_face_encoding_from_bgr(
    image_bgr: np.ndarray,
) -> tuple[Optional[list[float]], Optional[Any], list]:
    """Main face and its unit embedding (original + mirrored crop, see ``_FaceEngine.get``).

    Full-image light/JPEG TTA and synthetic glasses/condition variants were dropped on
    """
    faces = detect_faces(image_bgr)
    face = _best_face(faces)
    if face is None:
        return None, None, faces
    base = _normalized_embedding_row_from_face(face)
    return (None if base is None else base.tolist()), face, faces


def _face_crop_quality_metrics(image_bgr: np.ndarray, bbox) -> dict[str, Optional[float]]:
    h, w = image_bgr.shape[:2]
    try:
        x1, y1, x2, y2 = (int(round(float(bbox[i]))) for i in range(4))
    except (TypeError, ValueError, IndexError):
        return {"blur_laplacian_var": None, "brightness_mean": None}
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    if x2 <= x1 or y2 <= y1:
        return {"blur_laplacian_var": None, "brightness_mean": None}
    crop = image_bgr[y1:y2, x1:x2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return {
        "blur_laplacian_var": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
        "brightness_mean": float(np.mean(gray)),
    }


def _face_pose_meta(face: Any) -> dict[str, Optional[float]]:
    pose = getattr(face, "pose", None)
    if pose is None:
        return {"pose_yaw": None, "pose_pitch": None, "pose_roll": None}
    try:
        vals: list[Optional[float]] = [float(x) for x in np.asarray(pose).reshape(-1)[:3]]
    except (TypeError, ValueError):
        return {"pose_yaw": None, "pose_pitch": None, "pose_roll": None}
    while len(vals) < 3:
        vals.append(None)
    return {"pose_yaw": vals[0], "pose_pitch": vals[1], "pose_roll": vals[2]}


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
    media_control_root = os.path.abspath(os.path.join(str(settings.MEDIA_ROOT), "control_image"))
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

    Only paths are returned; files are read when the gallery is built.

    Args:
        staff: ``Staff`` instance.

    Returns:
        Up to ``FACE_TRAINING_LESSON_ATTENDANCE_MAX`` distinct readable paths.
    """
    if not getattr(settings, "FACE_TRAINING_INCLUDE_LESSON_ATTENDANCE", True):
        return []
    la = models.LessonAttendance
    la_manager = cast(Any, la).objects
    qs = (
        la_manager.filter(staff=staff, staff_image_path__isnull=False)
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
    return [str(row["path"]) for row in _collect_trusted_staff_face_sample_records_for_staff(staff)]


_TRUSTED_SAMPLES_ATTR = "_trusted_face_samples"


def _trusted_face_samples_qs():
    return (
        cast(Any, models.StaffFaceSample)
        .objects.filter(is_active=True, is_trusted=True)
        .order_by("-created_at", "-id")
    )


def _prefetch_trusted_face_samples(staff_list: list["models.Staff"]) -> None:
    """One query for every staff's trusted samples instead of one per staff (1:N search)."""
    from django.db.models import Prefetch, prefetch_related_objects

    prefetch_related_objects(
        staff_list,
        Prefetch(
            "face_samples", queryset=_trusted_face_samples_qs(), to_attr=_TRUSTED_SAMPLES_ATTR
        ),
    )


def _collect_trusted_staff_face_sample_records_for_staff(
    staff: "models.Staff",
) -> list[dict[str, object]]:
    """Active trusted Face Lab samples with metadata for runtime matching."""
    cap = max(0, int(getattr(settings, "FACE_BOOTSTRAP_MAX_ACTIVE_SAMPLES", 5)))
    if cap == 0:
        return []
    out: list[dict[str, object]] = []
    seen: set[str] = set()
    prefetched = getattr(staff, _TRUSTED_SAMPLES_ATTR, None)
    if prefetched is not None:
        rows: Iterable[Any] = prefetched
    else:
        rows = _trusted_face_samples_qs().filter(staff=staff).iterator(chunk_size=50)
    for row in rows:
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
        out.append(
            {
                "id": int(row.pk),
                "path": p,
                "angle": str(row.angle or ""),
                "with_glasses": bool(row.with_glasses),
                "probe_eyeglasses_likely": row.probe_eyeglasses_likely,
                "updated_at": (row.updated_at.isoformat() if row.updated_at is not None else ""),
            }
        )
    return out


def _runtime_embedding_rows_from_path(image_path: str) -> list[np.ndarray]:
    if not image_path or not os.path.isfile(image_path):
        return []
    image = imread_bgr(image_path)
    if image is None:
        return []
    embedding, _face, _faces = _create_face_encoding_from_bgr(preprocess_image(image))
    return [] if embedding is None else [np.asarray(embedding, dtype=np.float64)]


def create_face_encoding(image_or_path):
    """
    Creates a face embedding using the AdaFace model.

    Args:
        image_or_path (numpy.ndarray or str): Image array or image file path.

    Returns:
        list or None: Face embedding or None if failed.
    """
    try:
        load_face_engine()
        if isinstance(image_or_path, str):
            if not os.path.exists(image_or_path):
                logger.warning("Image file not found: %s", image_or_path)
                return None

            image = imread_bgr(image_or_path)
            if image is None:
                logger.warning("Failed to load image: %s", image_or_path)
                return None

            image = preprocess_image(image)
        else:
            if not isinstance(image_or_path, np.ndarray):
                logger.warning("Invalid image format, expected numpy array.")
                return None
            image = image_or_path

        embedding, face, _faces = _create_face_encoding_from_bgr(image)
        if face is None or embedding is None:
            logger.warning("No face detected in image %s", str(image_or_path))
            return None

        return embedding

    except Exception as e:
        logger.error("Ошибка при создании encoding: %s", e)
        return None


def create_face_encoding_with_probe_meta(
    image_bgr: np.ndarray,
) -> tuple[Optional[list[float]], dict[str, object]]:
    """
    AdaFace embedding plus conservative probe quality hints (BGR image).

    Returns:
        (embedding list or None, meta with quality_pass, det_score, face_area_ratio, ...).
    """
    try:
        load_face_engine()
        if not isinstance(image_bgr, np.ndarray):
            return None, {"face_present": False, "quality_pass": False}

        embedding, face, _faces = _create_face_encoding_from_bgr(image_bgr)
        if face is None or embedding is None:
            return None, {"face_present": False, "quality_pass": False}

        det_raw = getattr(face, "det_score", None)
        det_f = float(det_raw) if det_raw is not None else None
        bbox = face.bbox
        h, w = int(image_bgr.shape[0]), int(image_bgr.shape[1])
        area = _bbox_area(bbox)
        denom = float(max(1, h * w))
        face_ratio = float(area) / denom

        min_det = float(getattr(settings, "FACE_VERIFY_PROBE_DET_SCORE_MIN", 0.35))
        min_face = float(getattr(settings, "FACE_VERIFY_PROBE_FACE_AREA_RATIO_MIN", 0.008))
        quality_pass = True
        qreasons: list[str] = []
        if det_f is not None and det_f < min_det:
            quality_pass = False
            qreasons.append("low_det_score")
        if face_ratio < min_face:
            quality_pass = False
            qreasons.append("small_face")
        quality_metrics = _face_crop_quality_metrics(image_bgr, bbox)

        pose_meta = _face_pose_meta(face)
        yaw = pose_meta.get("pose_yaw")
        pitch = pose_meta.get("pose_pitch")
        max_yaw = float(getattr(settings, "FACE_VERIFY_PROBE_MAX_ABS_YAW", 40.0))
        max_pitch = float(getattr(settings, "FACE_VERIFY_PROBE_MAX_ABS_PITCH", 35.0))
        if max_yaw > 0 and isinstance(yaw, (int, float)) and abs(float(yaw)) > max_yaw:
            quality_pass = False
            qreasons.append("face_yaw_too_large")
        if max_pitch > 0 and isinstance(pitch, (int, float)) and abs(float(pitch)) > max_pitch:
            quality_pass = False
            qreasons.append("face_pitch_too_large")

        return embedding, {
            "face_present": True,
            "det_score": det_f,
            "face_area_ratio": face_ratio,
            "quality_pass": quality_pass,
            "quality_reason_codes": qreasons,
            **quality_metrics,
            **pose_meta,
        }
    except Exception as e:
        logger.error("create_face_encoding_with_probe_meta: %s", e)
        return None, {"face_present": False, "quality_pass": False}


def _gallery_source_record(source: object) -> dict[str, object]:
    if isinstance(source, Mapping):
        path = str(source.get("path") or source.get("image_path") or "")
        source_name = str(source.get("source") or "unknown")
        trusted = bool(source.get("trusted", False))
    else:
        path = str(source)
        source_name = "unknown"
        trusted = False
    return {"path": path, "source": source_name, "trusted": trusted}


def _gallery_meta_float(meta: Mapping[str, object], key: str) -> Optional[float]:
    value = meta.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _gallery_object_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _gallery_enrollment_quality_reject_reasons(
    meta: Mapping[str, object],
) -> list[str]:
    reasons: list[str] = []
    if not bool(meta.get("face_present", False)):
        reasons.append("no_face")
        return reasons

    checks: tuple[tuple[str, str, str, float], ...] = (
        (
            "det_score",
            "FACE_GALLERY_ENROLLMENT_DET_SCORE_MIN",
            "gallery_low_det_score",
            0.45,
        ),
        (
            "face_area_ratio",
            "FACE_GALLERY_ENROLLMENT_FACE_AREA_RATIO_MIN",
            "gallery_small_face",
            0.012,
        ),
        (
            "blur_laplacian_var",
            "FACE_GALLERY_ENROLLMENT_BLUR_MIN",
            "gallery_blurry_face",
            18.0,
        ),
        (
            "brightness_mean",
            "FACE_GALLERY_ENROLLMENT_BRIGHTNESS_MIN",
            "gallery_too_dark",
            30.0,
        ),
    )
    for meta_key, setting_name, reason, default in checks:
        value = _gallery_meta_float(meta, meta_key)
        minimum = float(getattr(settings, setting_name, default))
        if minimum > 0 and value is not None and value < minimum:
            reasons.append(reason)

    bright = _gallery_meta_float(meta, "brightness_mean")
    max_brightness = float(getattr(settings, "FACE_GALLERY_ENROLLMENT_BRIGHTNESS_MAX", 232.0))
    if max_brightness < 255 and bright is not None and bright > max_brightness:
        reasons.append("gallery_too_bright")

    yaw = _gallery_meta_float(meta, "pose_yaw")
    max_yaw = float(getattr(settings, "FACE_GALLERY_ENROLLMENT_MAX_ABS_YAW", 38.0))
    if max_yaw > 0 and yaw is not None and abs(yaw) > max_yaw:
        reasons.append("gallery_yaw_too_large")

    pitch = _gallery_meta_float(meta, "pose_pitch")
    max_pitch = float(getattr(settings, "FACE_GALLERY_ENROLLMENT_MAX_ABS_PITCH", 32.0))
    if max_pitch > 0 and pitch is not None and abs(pitch) > max_pitch:
        reasons.append("gallery_pitch_too_large")
    return reasons


def _gallery_quality_rank(meta: Mapping[str, object], source: str) -> float:
    source_bonus = {
        "avatar": 0.18,
        "staff_face_sample": 0.15,
        "face_sample": 0.15,
        "lesson_attendance": 0.0,
        "attendance": 0.0,
    }.get(source, 0.05)
    det = _gallery_meta_float(meta, "det_score") or 0.50
    face_area = _gallery_meta_float(meta, "face_area_ratio") or 0.0
    blur = _gallery_meta_float(meta, "blur_laplacian_var") or 0.0
    bright = _gallery_meta_float(meta, "brightness_mean")
    if bright is None:
        exposure_score = 0.55
    else:
        exposure_score = 1.0 - min(abs(bright - 128.0) / 128.0, 1.0)
    return float(
        source_bonus
        + 0.42 * min(max(det, 0.0), 1.0)
        + 0.22 * min(max(face_area / 0.08, 0.0), 1.0)
        + 0.20 * min(max(blur / 180.0, 0.0), 1.0)
        + 0.16 * exposure_score
    )


def _gallery_pad_reject_reasons(
    image_bgr: np.ndarray,
    *,
    trusted_source: bool = False,
) -> tuple[list[str], dict[str, object]]:
    if not bool(getattr(settings, "FACE_GALLERY_ENROLLMENT_PAD_VALIDATE", True)):
        return [], {"pad_skipped": True}

    try:
        from monitoring_app.photo_pad import STATUS_CLEAN, check_photo_bgr

        pad = check_photo_bgr(image_bgr)
    except Exception as exc:
        return ["gallery_pad_error"], {"pad_error": str(exc)}

    status = str(getattr(pad, "status", "") or "")
    trust = getattr(pad, "trust_confirmed", None)
    risk = float(getattr(pad, "risk_score", 0.0) or 0.0)
    tags = list(getattr(pad, "tags", []) or [])
    max_risk = float(getattr(settings, "FACE_GALLERY_ENROLLMENT_PAD_MAX_RISK", 0.42))
    reasons: list[str] = []
    if status != STATUS_CLEAN:
        reasons.append(f"gallery_pad_{status or 'unknown'}")
    if trust is not True:
        reasons.append("gallery_pad_not_confirmed")
    if risk > max_risk:
        reasons.append("gallery_pad_high_risk")
    if trusted_source and reasons == ["gallery_pad_not_confirmed"]:
        reasons = []
    return reasons, {
        "pad_status": status,
        "pad_trust_confirmed": trust,
        "pad_risk_score": risk,
        "pad_tags": tags[:12],
    }


def _gallery_reject_record(
    path: str,
    source: str,
    reasons: list[str],
    extra: Mapping[str, object] | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "path": path,
        "source": source,
        "accepted": False,
        "reasons": list(dict.fromkeys(reasons)),
    }
    if extra:
        row.update(dict(extra))
    return row


def create_vetted_gallery_embeddings_from_images(
    image_sources: Iterable[object],
    *,
    run_pad: Optional[bool] = None,
) -> tuple[list[list[float]], dict[str, object]]:
    """Build a conservative real-person gallery from mixed live/photo sources.

    ``ATTENDANCE_ROOT`` photos are useful only when they are not blindly trusted:
    every candidate is decoded, PAD-checked, quality-checked, compared with the
    trusted anchor set (avatar / StaffFaceSample), then de-duplicated.
    """
    if run_pad is None:
        run_pad = bool(getattr(settings, "FACE_GALLERY_ENROLLMENT_PAD_VALIDATE", True))

    records = [_gallery_source_record(src) for src in image_sources]
    accepted: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    seen_paths: set[str] = set()

    for src in records:
        path = str(src["path"])
        source = str(src["source"])
        trusted = bool(src["trusted"])
        if not path:
            rejected.append(_gallery_reject_record(path, source, ["empty_path"]))
            continue
        abs_path = os.path.abspath(path)
        if abs_path in seen_paths:
            continue
        seen_paths.add(abs_path)
        if not os.path.exists(abs_path):
            rejected.append(_gallery_reject_record(abs_path, source, ["missing_file"]))
            continue

        image = imread_bgr(abs_path)
        if image is None:
            rejected.append(_gallery_reject_record(abs_path, source, ["decode_error"]))
            continue
        image = preprocess_image(image)

        pad_meta: dict[str, object] = {}
        if run_pad:
            pad_reasons, pad_meta = _gallery_pad_reject_reasons(
                image,
                trusted_source=trusted,
            )
            if pad_reasons:
                rejected.append(_gallery_reject_record(abs_path, source, pad_reasons, pad_meta))
                continue

        embedding, meta = create_face_encoding_with_probe_meta(image)
        if embedding is None:
            rejected.append(
                _gallery_reject_record(
                    abs_path,
                    source,
                    ["embedding_failed"],
                    {**pad_meta, **meta},
                )
            )
            continue
        q_reasons = _gallery_enrollment_quality_reject_reasons(meta)
        if q_reasons:
            rejected.append(
                _gallery_reject_record(
                    abs_path,
                    source,
                    q_reasons,
                    {**pad_meta, **meta},
                )
            )
            continue

        row = _l2_normalize_embedding_rows(np.asarray(embedding, dtype=np.float64).reshape(1, -1))[
            0
        ]
        accepted.append(
            {
                "path": abs_path,
                "source": source,
                "trusted": trusted,
                "embedding": row,
                "quality_rank": _gallery_quality_rank(meta, source),
                "meta": {**pad_meta, **meta},
            }
        )

    anchor_sources = {"avatar", "staff_face_sample", "face_sample"}
    attendance_sources = {"lesson_attendance", "attendance"}
    anchors = [
        cast(np.ndarray, item["embedding"])
        for item in accepted
        if str(item["source"]) in anchor_sources or bool(item["trusted"])
    ]
    if anchors:
        anchor_mat = np.vstack(anchors)
        anchor_centroid = _normalized_centroid_row(anchor_mat)
        min_anchor = float(getattr(settings, "FACE_GALLERY_ATTENDANCE_MIN_ANCHOR_COS", 0.54))
        if anchor_centroid is not None and min_anchor > 0:
            kept: list[dict[str, object]] = []
            for item in accepted:
                row = cast(np.ndarray, item["embedding"])
                source = str(item["source"])
                cos = float(row @ anchor_centroid.reshape(-1))
                item["anchor_cosine"] = cos
                if source in {"lesson_attendance", "attendance"} and cos < min_anchor:
                    rejected.append(
                        _gallery_reject_record(
                            str(item["path"]),
                            source,
                            ["gallery_anchor_mismatch"],
                            {"anchor_cosine": cos, "anchor_min": min_anchor},
                        )
                    )
                    continue
                kept.append(item)
            accepted = kept
    else:
        min_no_anchor = max(
            1, int(getattr(settings, "FACE_GALLERY_ATTENDANCE_MIN_NO_ANCHOR_COUNT", 3))
        )
        attendance_count = sum(1 for item in accepted if str(item["source"]) in attendance_sources)
        if attendance_count and attendance_count < min_no_anchor:
            kept = []
            for item in accepted:
                source = str(item["source"])
                if source in attendance_sources:
                    rejected.append(
                        _gallery_reject_record(
                            str(item["path"]),
                            source,
                            ["gallery_missing_anchor"],
                            {
                                "attendance_count": attendance_count,
                                "min_no_anchor_count": min_no_anchor,
                            },
                        )
                    )
                    continue
                kept.append(item)
            accepted = kept

    if len(accepted) >= 3:
        mat_for_centroid = np.vstack([cast(np.ndarray, item["embedding"]) for item in accepted])
        centroid = _normalized_centroid_row(mat_for_centroid)
        min_centroid = float(getattr(settings, "FACE_GALLERY_ENROLLMENT_MIN_CENTROID_COS", 0.46))
        if centroid is not None and min_centroid > 0:
            kept = []
            for item in accepted:
                row = cast(np.ndarray, item["embedding"])
                cos = float(row @ centroid.reshape(-1))
                item["centroid_cosine"] = cos
                if cos < min_centroid:
                    rejected.append(
                        _gallery_reject_record(
                            str(item["path"]),
                            str(item["source"]),
                            ["gallery_centroid_outlier"],
                            {"centroid_cosine": cos, "centroid_min": min_centroid},
                        )
                    )
                    continue
                kept.append(item)
            accepted = kept

    dedupe_max = float(getattr(settings, "FACE_GALLERY_REAL_DEDUPE_MAX_COS", 0.9975))
    cap = max(1, int(getattr(settings, "FACE_GALLERY_REAL_MAX_PROTOTYPES", 48)))
    source_priority = {
        "avatar": 0,
        "staff_face_sample": 1,
        "face_sample": 1,
        "lesson_attendance": 2,
        "attendance": 2,
    }
    accepted.sort(
        key=lambda item: (
            source_priority.get(str(item["source"]), 3),
            -_gallery_object_float(item.get("quality_rank")),
        )
    )
    kept_rows: list[np.ndarray] = []
    kept_records: list[dict[str, object]] = []
    processed_ids: set[int] = set()
    for item in accepted:
        processed_ids.add(id(item))
        row = cast(np.ndarray, item["embedding"])
        if kept_rows:
            sims = np.vstack(kept_rows) @ row.reshape(-1, 1)
            if float(np.max(sims)) >= dedupe_max:
                rejected.append(
                    _gallery_reject_record(
                        str(item["path"]),
                        str(item["source"]),
                        ["gallery_near_duplicate"],
                        {"dedupe_max_cos": dedupe_max},
                    )
                )
                continue
        kept_rows.append(row)
        kept_records.append(item)
        if len(kept_rows) >= cap:
            break

    for item in accepted:
        if id(item) in processed_ids:
            continue
        rejected.append(
            _gallery_reject_record(
                str(item["path"]),
                str(item["source"]),
                ["gallery_cap_reached"],
                {"cap": cap},
            )
        )

    accepted_public: list[dict[str, object]] = []
    for item in kept_records:
        meta = dict(cast(Mapping[str, object], item.get("meta", {})))
        accepted_public.append(
            {
                "path": item["path"],
                "source": item["source"],
                "quality_rank": round(_gallery_object_float(item.get("quality_rank")), 4),
                "det_score": meta.get("det_score"),
                "face_area_ratio": meta.get("face_area_ratio"),
                "blur_laplacian_var": meta.get("blur_laplacian_var"),
                "brightness_mean": meta.get("brightness_mean"),
                "pose_yaw": meta.get("pose_yaw"),
                "pose_pitch": meta.get("pose_pitch"),
                "pad_status": meta.get("pad_status"),
                "pad_risk_score": meta.get("pad_risk_score"),
                "anchor_cosine": item.get("anchor_cosine"),
                "centroid_cosine": item.get("centroid_cosine"),
            }
        )

    reject_counter: Counter[str] = Counter()
    for row in rejected:
        reasons = row.get("reasons", [])
        if not isinstance(reasons, list):
            continue
        for reason in reasons:
            reject_counter[str(reason)] += 1

    report: dict[str, object] = {
        "input_count": len(records),
        "decoded_candidate_count": len(accepted) + len(rejected),
        "accepted_count": len(kept_rows),
        "rejected_count": len(rejected),
        "accepted_by_source": dict(Counter(str(x["source"]) for x in kept_records)),
        "rejected_by_reason": dict(reject_counter),
        "accepted": accepted_public,
        "rejected": rejected,
    }
    return [row.tolist() for row in kept_rows], report


def _l2_normalize_embedding_rows(mat: np.ndarray) -> np.ndarray:
    mat = np.asarray(mat, dtype=np.float64)
    if mat.ndim == 1:
        mat = mat.reshape(1, -1)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-10)
    return mat / norms


def _probe_embedding_row(embedding) -> np.ndarray:
    """Вектор лица (1D) из AdaFace; без «схлопывания» в (dim,) при одном лице."""
    v = np.asarray(embedding, dtype=np.float64)
    if v.size == 0:
        raise ValueError("Пустой эмбеддинг лица")
    return v.reshape(-1)


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


def _normalized_centroid_row(mat: np.ndarray) -> Optional[np.ndarray]:
    """Robust centroid over normalized face embeddings."""
    if mat.size == 0:
        return None
    m = _l2_normalize_embedding_rows(mat)
    if int(m.shape[0]) == 1:
        c = m[0]
    else:
        c = np.median(m, axis=0)
    norm = float(np.linalg.norm(c))
    if norm < 1e-10:
        return None
    return (c / norm).reshape(1, -1)


def _add_runtime_centroid_prototypes(
    source_blocks: list[tuple[str, np.ndarray]],
) -> tuple[list[np.ndarray], int]:
    """Add stable template aggregates, inspired by set/template face matching."""
    if not bool(getattr(settings, "FACE_RUNTIME_ADD_CENTROID_PROTOTYPES", True)):
        return [], 0

    min_rows = max(2, int(getattr(settings, "FACE_RUNTIME_CENTROID_MIN_ROWS", 2)))
    out: list[np.ndarray] = []

    all_rows: list[np.ndarray] = []
    by_source: dict[str, list[np.ndarray]] = {}
    for source, block in source_blocks:
        b = _l2_normalize_embedding_rows(block)
        all_rows.append(b)
        by_source.setdefault(source, []).append(b)

    if all_rows:
        all_mat = np.vstack(all_rows)
        if int(all_mat.shape[0]) >= min_rows:
            c = _normalized_centroid_row(all_mat)
            if c is not None:
                out.append(c)

    for source, blocks in sorted(by_source.items()):
        if source == "avatar":
            continue
        mat = np.vstack(blocks)
        if int(mat.shape[0]) < max(3, min_rows):
            continue
        c = _normalized_centroid_row(mat)
        if c is not None:
            out.append(c)

    return out, len(out)


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
    Runtime gallery only: stored mask, live avatar file, trusted Face Lab samples,
    optional ``{pin}_gallery_real.npy``.

    Rows are L2-normalized and near-duplicate collapsed.
    """
    pin = _staff_pin(staff)
    signature = _staff_runtime_gallery_signature(staff)
    mem_cached = _staff_runtime_gallery_mem_cache.get(pin)
    if mem_cached and mem_cached[0] == signature:
        return mem_cached[1], dict(mem_cached[2])

    cache_path = _staff_runtime_gallery_cache_path(pin)
    disk_cached = _load_staff_runtime_gallery_cache(cache_path, signature)
    if disk_cached is not None:
        gallery, breakdown = disk_cached
        _staff_runtime_gallery_mem_cache[pin] = (
            signature,
            gallery,
            dict(breakdown),
        )
        return gallery, dict(breakdown)

    rows: list[np.ndarray] = []
    source_blocks: list[tuple[str, np.ndarray]] = []
    breakdown: dict[str, int] = {
        "mask_prototypes": 0,
        "avatar_prototypes": 0,
        "face_sample_prototypes": 0,
        "centroid_prototypes": 0,
        "gallery_real_npy_prototypes": 0,
    }

    try:
        fm = cast(Any, getattr(staff, "face_mask", None))
        if fm is not None and fm.mask_encoding:
            mm = _mask_json_to_matrix(fm.mask_encoding)
            if mm is not None:
                mm = np.asarray(mm, dtype=np.float64)
                rows.append(mm)
                source_blocks.append(("mask", mm))
                breakdown["mask_prototypes"] = int(mm.shape[0])
    except ObjectDoesNotExist:
        pass

    try:
        avatar = cast(Any, getattr(staff, "avatar", None))
        if avatar and getattr(avatar, "path", None):
            ap = str(avatar.path)
            if ap and os.path.isfile(ap):
                avatar_rows = _runtime_embedding_rows_from_path(ap)
                if avatar_rows:
                    avatar_mat = np.vstack(avatar_rows)
                    rows.append(avatar_mat)
                    source_blocks.append(("avatar", avatar_mat))
                    breakdown["avatar_prototypes"] = int(avatar_mat.shape[0])
    except Exception as e:
        logger.warning("Avatar embedding for runtime gallery skipped for %s: %s", staff.pin, e)

    if bool(getattr(settings, "FACE_RUNTIME_INCLUDE_FACE_SAMPLES", True)):
        sample_rows: list[np.ndarray] = []
        for sample in _collect_trusted_staff_face_sample_records_for_staff(staff):
            p = str(sample.get("path") or "")
            if not p or not os.path.isfile(p):
                continue
            try:
                one_rows = _runtime_embedding_rows_from_path(p)
            except Exception as exc:
                logger.warning(
                    "Face sample embedding skipped for %s sample=%s: %s",
                    staff.pin,
                    sample.get("id"),
                    exc,
                )
                continue
            sample_rows.extend(one_rows)
        if sample_rows:
            sample_mat = np.vstack(sample_rows)
            rows.append(sample_mat)
            source_blocks.append(("face_sample", sample_mat))
            breakdown["face_sample_prototypes"] = int(sample_mat.shape[0])

    base_dir: Optional[str] = None
    try:
        avatar = cast(Any, getattr(staff, "avatar", None))
        if avatar and getattr(avatar, "path", None):
            base_dir = os.path.dirname(str(avatar.path))
    except Exception:
        base_dir = None

    if base_dir:
        gr_path = os.path.join(base_dir, f"{pin}_gallery_real.npy")
        if os.path.isfile(gr_path):
            try:
                e = np.load(gr_path)
                if e.ndim == 1:
                    e = e.reshape(1, -1)
                if e.size > 0:
                    real_mat = e.astype(np.float64)
                    rows.append(real_mat)
                    source_blocks.append(("gallery_real", real_mat))
                    breakdown["gallery_real_npy_prototypes"] = int(e.shape[0])
            except Exception as e:
                logger.warning("gallery_real.npy skipped for %s: %s", staff.pin, e)

    gal: Optional[np.ndarray]
    if not rows:
        gal = None
    else:
        centroid_rows, centroid_count = _add_runtime_centroid_prototypes(source_blocks)
        if centroid_rows:
            rows.extend(centroid_rows)
            breakdown["centroid_prototypes"] = centroid_count
        gal = np.vstack(rows)
        gal = _l2_normalize_embedding_rows(gal)
        gal = _dedupe_normalized_rows(gal, min_cos=0.999)

    _save_staff_runtime_gallery_cache(cache_path, signature, gal, breakdown)
    _staff_runtime_gallery_mem_cache[pin] = (signature, gal, dict(breakdown))
    return gal, breakdown


def build_multi_staff_runtime_gallery_matrix(
    staff_iterable: Iterable["models.Staff"],
) -> tuple[np.ndarray, list["models.Staff"]]:
    """Stack runtime verification prototypes from many staff rows for 1:N search.

    For each staff member, calls :func:`build_runtime_gallery_embeddings`.
    Same runtime sources as verify.

    Returns:
        ``G`` with shape ``(n_prototypes, dim)`` (rows L2-normalized) and
        ``owners[i]`` = staff owning prototype row ``i``.

    Raises:
        ValueError: If no prototypes exist for any staff in the iterable.
    """
    global _multi_staff_runtime_gallery_mem_cache

    staff_list = list(staff_iterable)
    staff_pins = tuple(_staff_pin(staff) for staff in staff_list)

    mem_cached = _multi_staff_runtime_gallery_mem_cache
    if mem_cached and mem_cached[0] == staff_pins:
        owners_by_pin = {_staff_pin(staff): staff for staff in staff_list}
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
            tuple(_staff_pin(owner) for owner in owners),
        )
        return matrix, owners

    owners: list[models.Staff] = []
    owner_pins: list[str] = []
    blocks: list[np.ndarray] = []
    _prefetch_trusted_face_samples(staff_list)
    for staff in staff_list:
        gal, _bd = build_runtime_gallery_embeddings(staff)
        if gal is None or gal.size == 0:
            continue
        owners.extend([staff] * int(gal.shape[0]))
        owner_pins.extend([_staff_pin(staff)] * int(gal.shape[0]))
        blocks.append(gal)
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
    """Probe vs the staff member's runtime gallery: score = best cosine over its photos.

    One threshold ``FACE_VERIFY_THRESHOLD`` for any gallery size, plus the nearest-other-
    staff guard (look-alikes / one person on two accounts).
    """
    gal, gallery_breakdown = build_runtime_gallery_embeddings(staff)
    if gal is None or gal.size == 0:
        raise ValueError("No gallery embeddings available for this staff member.")

    p = _l2_normalize_embedding_rows(np.asarray(probe_embedding, dtype=np.float64).reshape(1, -1))
    score = float(np.max(gal @ p[0]))
    thr = settings.FACE_VERIFY_THRESHOLD
    meta: dict[str, Any] = {
        "gallery_templates": int(gal.shape[0]),
        "gallery_breakdown": dict(gallery_breakdown),
        "threshold_used": thr,
        "max_cosine": score,
    }
    _apply_impostor_gap_guard(staff, p, score, meta)
    verified = score >= thr and not bool(meta.get("impostor_ambiguous"))
    return verified, score, meta


def _apply_impostor_gap_guard(
    staff: "models.Staff",
    probe_normalized: np.ndarray,
    claimed_score: float,
    meta: dict[str, Any],
) -> None:
    """Reject high absolute matches when another staff member is nearly as close."""
    meta["impostor_guard_checked"] = False
    meta["impostor_ambiguous"] = False
    if not bool(getattr(settings, "FACE_VERIFY_IMPOSTOR_GAP_ENABLE", True)):
        meta["impostor_guard_disabled"] = True
        return

    staff_manager = cast(Any, models.Staff).objects
    staff_qs = list(
        staff_manager.filter(Q(face_mask__isnull=False) | (Q(avatar__isnull=False) & ~Q(avatar="")))
        .select_related("department", "face_mask")
        .order_by("pin")
    )
    if len(staff_qs) <= 1:
        meta["impostor_guard_checked"] = True
        meta["impostor_guard_note"] = "no_other_staff_gallery"
        return

    try:
        matrix, owners = build_multi_staff_runtime_gallery_matrix(staff_qs)
    except Exception as exc:
        meta["impostor_guard_error"] = str(exc)
        return

    if matrix.ndim != 2 or matrix.shape[1] != probe_normalized.shape[1]:
        meta["impostor_guard_error"] = "embedding_dimension_mismatch"
        return

    other_indices = [i for i, owner in enumerate(owners) if owner.pk != staff.pk]
    if not other_indices:
        meta["impostor_guard_checked"] = True
        meta["impostor_guard_note"] = "no_other_staff_prototypes"
        return

    other_matrix = matrix[other_indices]
    sims = (other_matrix @ probe_normalized.T).ravel()
    best_local = int(np.argmax(sims))
    best_global = other_indices[best_local]
    nearest_owner = owners[best_global]
    nearest_score = float(sims[best_local])
    gap = float(claimed_score - nearest_score)
    gap_min = settings.FACE_VERIFY_IMPOSTOR_GAP_MIN
    other_min = settings.FACE_VERIFY_THRESHOLD
    ambiguous = nearest_score >= other_min and gap < gap_min

    meta.update(
        {
            "impostor_guard_checked": True,
            "nearest_impostor_pin": getattr(nearest_owner, "pin", None),
            "nearest_impostor_similarity": nearest_score,
            "impostor_gap": gap,
            "impostor_gap_min": gap_min,
            "impostor_min_other_score": other_min,
            "impostor_ambiguous": bool(ambiguous),
        }
    )


def _classify_runtime_gallery_matches(
    faces: list,
    embeddings_normalized: np.ndarray,
    staff_embeddings_normalized: np.ndarray,
    row_owners: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Run exact cosine search against a prepared runtime gallery matrix.

    Args:
        faces: Detected face objects from AdaFace.
        embeddings_normalized: Probe embeddings with shape ``(n, dim)``.
        staff_embeddings_normalized: Gallery prototype matrix.
        row_owners: Owner row for each gallery prototype.

    Returns:
        Recognized staff rows and unknown face rows.
    """
    thr = settings.FACE_RECOGNITION_THRESHOLD
    gap_min = settings.FACE_RECOGNITION_MIN_NEIGHBOR_GAP

    recognized_staff: list[dict[str, Any]] = []
    unknown_faces: list[dict[str, Any]] = []

    owner_pks = np.fromiter((int(o.pk) for o in row_owners), dtype=np.int64, count=len(row_owners))
    for idx, face in enumerate(faces):
        bbox = face.bbox.astype(int).tolist()
        sims_all = np.nan_to_num(
            (staff_embeddings_normalized @ embeddings_normalized[idx]).ravel(), nan=-1.0
        )
        best_i = int(np.argmax(sims_all))
        similarity, staff_best = float(sims_all[best_i]), row_owners[best_i]
        others = sims_all[owner_pks != owner_pks[best_i]]
        second_other_sim = float(others.max()) if others.size else -1.0
        gap = 1.0 if second_other_sim < -0.5 else similarity - second_other_sim

        accept = similarity >= thr and gap >= gap_min

        if accept:
            recognized_staff.append(
                {
                    "pin": staff_best.pin,
                    "name": staff_best.name,
                    "surname": staff_best.surname,
                    "department": (staff_best.department.name if staff_best.department else None),
                    "similarity": similarity,
                    "neighbor_gap": gap,
                    "bbox": bbox,
                    "avatar_url": (staff_best.avatar.url if staff_best.avatar else None),
                }
            )
        else:
            unknown_faces.append(
                {
                    "status": "unknown",
                    "bbox": bbox,
                    "best_similarity": similarity,
                    "neighbor_gap": gap,
                }
            )

    return recognized_staff, unknown_faces


def recognize_faces_in_image(image_file):
    """Recognize staff faces using the same **runtime gallery** rules as verify.

    Exact cosine search over the full multi-staff matrix
    (:func:`build_multi_staff_runtime_gallery_matrix`). A face is recognized when its
    top-1 score >= ``FACE_RECOGNITION_THRESHOLD`` and beats the best other staff
    member by ``FACE_RECOGNITION_MIN_NEIGHBOR_GAP``.

    Args:
        image_file (InMemoryUploadedFile): Uploaded image file.

    Returns:
        tuple: (recognized_staff, unknown_faces)

    Raises:
        ValidationError: If recognition fails.
    """
    try:
        load_face_engine()
        img = load_image_from_memory(image_file)
        faces = detect_faces(img)
        min_face = float(getattr(settings, "FACE_VERIFY_PROBE_FACE_AREA_RATIO_MIN", 0.008))
        frame_area = float(max(1, int(img.shape[0]) * int(img.shape[1])))
        faces = [f for f in faces if _bbox_area(f.bbox) / frame_area >= min_face]

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

        staff_manager = cast(Any, models.Staff).objects
        staff_qs = list(
            staff_manager.filter(
                Q(face_mask__isnull=False) | (Q(avatar__isnull=False) & ~Q(avatar=""))
            )
            .select_related("department", "face_mask")
            .order_by("pin")
        )
        if not staff_qs:
            raise ValidationError("В базе нет сотрудников с аватаром или сохранённой маской лица.")

        def ensure_dim_matches(matrix: np.ndarray) -> None:
            dim_staff = int(matrix.shape[1])
            if dim_staff != dim_face:
                raise ValidationError(
                    f"Размерность эталонов в базе ({dim_staff}) не совпадает с моделью "
                    f"распознавания ({dim_face})."
                )

        try:
            staff_embeddings_normalized, row_owners = build_multi_staff_runtime_gallery_matrix(
                staff_qs
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
