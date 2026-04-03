"""
Face-ID oriented augmentation for staff gallery training.

Goal: expand **intra-class** variation (same person, different capture conditions)
without destroying identity cues. Embeddings are built with ArcFace (`ml.py`);
augments must pass a face re-detection gate and stay close to the median
embedding (outlier filter).

We avoid ImageNet-style AutoAug / aggressive color jitter and **horizontal flip**
on ArcFace-aligned crops (canonical pose; flip hurts consistency with inference).
"""
import logging
import os
from typing import Callable, Dict, Optional, Tuple

import cv2
import numpy as np
from django.conf import settings
from django.db.models import QuerySet
from monitoring_app import ml, models

logger = logging.getLogger(__name__)

try:
    from insightface.utils import face_align as _insightface_face_align
except ImportError:
    _insightface_face_align = None

FACE_ALIGN_SIZE = 112
FACE_CROP_OUT_SIZE = 256
FACE_SQUARE_PAD_RATIO = 1.08
RANDOM_AUGMENTS_TARGET = 20
RANDOM_AUGMENT_MAX_ATTEMPTS = 72

FaceIdPresetFn = Callable[[np.ndarray], np.ndarray]


def expand_face_bbox(
    face_coords,
    image_shape,
    expand_ratio_left=0.1,
    expand_ratio_right=0.1,
    expand_ratio_top=0.1,
    expand_ratio_bottom=0.2,
):
    x_min, y_min, x_max, y_max = face_coords
    height, width = image_shape[:2]
    face_width = x_max - x_min
    face_height = y_max - y_min
    x_min_expanded = max(0, int(x_min - face_width * expand_ratio_left))
    y_min_expanded = max(0, int(y_min - face_height * expand_ratio_top))
    x_max_expanded = min(width, int(x_max + face_width * expand_ratio_right))
    y_max_expanded = min(height, int(y_max + face_height * expand_ratio_bottom))
    return x_min_expanded, y_min_expanded, x_max_expanded, y_max_expanded


def square_face_crop_rgb(
    image_rgb: np.ndarray,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    out_size: int = FACE_CROP_OUT_SIZE,
) -> Optional[np.ndarray]:
    """Crop expanded face box, pad to square, resize to out_size (RGB)."""
    h, w = image_rgb.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    if x2 <= x1 or y2 <= y1:
        return None
    crop = image_rgb[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    ch, cw = crop.shape[:2]
    side = int(max(ch, cw) * FACE_SQUARE_PAD_RATIO)
    side = max(side, 32)
    sq = np.zeros((side, side, 3), dtype=np.uint8)
    yoff = (side - ch) // 2
    xoff = (side - cw) // 2
    sq[yoff : yoff + ch, xoff : xoff + cw] = crop
    return cv2.resize(sq, (out_size, out_size), interpolation=cv2.INTER_AREA)


def _validate_face_present_rgb(image_rgb: np.ndarray) -> bool:
    return get_face_bbox(image_rgb) is not None


def insightface_aligned_face_rgb(image_rgb: np.ndarray) -> Optional[np.ndarray]:
    """
    5-point ArcFace alignment to FACE_ALIGN_SIZE, resized to FACE_CROP_OUT_SIZE.
    Falls back to caller when insightface or landmarks are unavailable.
    """
    if _insightface_face_align is None:
        return None
    try:
        ml.load_arcface_model()
        inst = ml.arcface_model_holder.instance
        if inst is None:
            return None
        face_input = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
        faces = inst.get(face_input)
        if not faces:
            return None
        face = faces[0]
        kps = getattr(face, "kps", None)
        if kps is None:
            return None
        try:
            aligned_bgr = _insightface_face_align.norm_crop(
                face_input,
                landmark=kps,
                image_size=FACE_ALIGN_SIZE,
                mode="arcface",
            )
        except TypeError:
            aligned_bgr = _insightface_face_align.norm_crop(
                face_input, landmark=kps, image_size=FACE_ALIGN_SIZE
            )
        aligned_rgb = cv2.cvtColor(aligned_bgr, cv2.COLOR_BGR2RGB)
        if FACE_CROP_OUT_SIZE != FACE_ALIGN_SIZE:
            aligned_rgb = cv2.resize(
                aligned_rgb,
                (FACE_CROP_OUT_SIZE, FACE_CROP_OUT_SIZE),
                interpolation=cv2.INTER_CUBIC,
            )
        return aligned_rgb
    except Exception as e:
        logger.debug("InsightFace alignment skipped: %s", e)
        return None



def _preset_dim_light(rgb: np.ndarray) -> np.ndarray:
    f = rgb.astype(np.float32) * 0.84
    return np.clip(f, 0, 255).astype(np.uint8)


def _preset_bright_room(rgb: np.ndarray) -> np.ndarray:
    f = rgb.astype(np.float32) * 1.11 + 6.0
    return np.clip(f, 0, 255).astype(np.uint8)


def _preset_flat_lighting(rgb: np.ndarray) -> np.ndarray:
    f = rgb.astype(np.float32)
    mean = f.mean(axis=(0, 1), keepdims=True)
    return np.clip((f - mean) * 0.84 + mean, 0, 255).astype(np.uint8)


def _preset_stronger_contrast(rgb: np.ndarray) -> np.ndarray:
    f = rgb.astype(np.float32)
    mean = f.mean(axis=(0, 1), keepdims=True)
    return np.clip((f - mean) * 1.16 + mean, 0, 255).astype(np.uint8)


def _preset_wb_warm(rgb: np.ndarray) -> np.ndarray:
    f = rgb.astype(np.float32)
    f[:, :, 0] *= 1.06
    f[:, :, 1] *= 1.02
    f[:, :, 2] *= 0.94
    return np.clip(f, 0, 255).astype(np.uint8)


def _preset_wb_cool(rgb: np.ndarray) -> np.ndarray:
    f = rgb.astype(np.float32)
    f[:, :, 0] *= 0.95
    f[:, :, 2] *= 1.07
    return np.clip(f, 0, 255).astype(np.uint8)


def _preset_gamma_lift_shadows(rgb: np.ndarray) -> np.ndarray:
    x = rgb.astype(np.float32) / 255.0
    x = np.power(np.clip(x, 1e-6, 1.0), 1.09)
    return np.clip(x * 255.0, 0, 255).astype(np.uint8)


def _preset_gamma_brighten_mids(rgb: np.ndarray) -> np.ndarray:
    x = rgb.astype(np.float32) / 255.0
    x = np.power(np.clip(x, 1e-6, 1.0), 0.90)
    return np.clip(x * 255.0, 0, 255).astype(np.uint8)


def _preset_jpeg_heavy(rgb: np.ndarray) -> np.ndarray:
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    ok, enc = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 58])
    if not ok:
        return rgb
    dec = cv2.imdecode(enc, cv2.IMREAD_COLOR)
    if dec is None:
        return rgb
    return cv2.cvtColor(dec, cv2.COLOR_BGR2RGB)


def _preset_jpeg_mild(rgb: np.ndarray) -> np.ndarray:
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    ok, enc = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    if not ok:
        return rgb
    dec = cv2.imdecode(enc, cv2.IMREAD_COLOR)
    if dec is None:
        return rgb
    return cv2.cvtColor(dec, cv2.COLOR_BGR2RGB)


def _preset_soft_focus(rgb: np.ndarray) -> np.ndarray:
    blur = cv2.GaussianBlur(rgb, (0, 0), 1.15)
    return cv2.addWeighted(rgb, 0.62, blur, 0.38, 0)


def _preset_unsharp_mild(rgb: np.ndarray) -> np.ndarray:
    blur = cv2.GaussianBlur(rgb, (0, 0), 0.95)
    out = cv2.addWeighted(rgb, 1.22, blur, -0.22, 0)
    return np.clip(out, 0, 255).astype(np.uint8)


def _preset_far_camera(rgb: np.ndarray) -> np.ndarray:
    """Downscale and upscale: cheap lens / distance / recompression pipeline."""
    h, w = rgb.shape[:2]
    small = cv2.resize(
        rgb, (max(w // 2, 96), max(h // 2, 96)), interpolation=cv2.INTER_AREA
    )
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)


def _preset_clahe_face_friendly(rgb: np.ndarray) -> np.ndarray:
    """Mild local contrast — uneven office light; kept weak to avoid halos."""
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(8, 8))
    l_eq = clahe.apply(l_ch)
    merged = cv2.merge([l_eq, a_ch, b_ch])
    return cv2.cvtColor(merged, cv2.COLOR_LAB2RGB)


def _preset_iso_noise(rgb: np.ndarray) -> np.ndarray:
    f = rgb.astype(np.float32)
    h, w = f.shape[:2]
    cy, cx = h // 2, w // 2
    seed = (
        int(f[cy, cx, 0]) << 16 | int(f[cy, cx, 1]) << 8 | int(f[cy, cx, 2])
    ) & 0xFFFFFFFF
    rng = np.random.default_rng(seed)
    noise = rng.normal(0.0, 2.4, rgb.shape).astype(np.float32)
    return np.clip(f + noise, 0, 255).astype(np.uint8)


def _preset_motion_blur_short(rgb: np.ndarray) -> np.ndarray:
    k = 5
    kernel = np.zeros((k, k), np.float32)
    kernel[k // 2, :] = 1.0 / k
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    bgr = cv2.filter2D(bgr, -1, kernel)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


FACE_ID_PRESET_AUGMENTS: Dict[str, FaceIdPresetFn] = {
    "dim_light": _preset_dim_light,
    "bright_room": _preset_bright_room,
    "flat_lighting": _preset_flat_lighting,
    "stronger_contrast": _preset_stronger_contrast,
    "wb_warm": _preset_wb_warm,
    "wb_cool": _preset_wb_cool,
    "gamma_lift_shadows": _preset_gamma_lift_shadows,
    "gamma_brighten_mids": _preset_gamma_brighten_mids,
    "jpeg_heavy": _preset_jpeg_heavy,
    "jpeg_mild": _preset_jpeg_mild,
    "soft_focus": _preset_soft_focus,
    "unsharp_mild": _preset_unsharp_mild,
    "far_camera": _preset_far_camera,
    "clahe_mild": _preset_clahe_face_friendly,
    "iso_noise": _preset_iso_noise,
    "motion_blur_short": _preset_motion_blur_short,
}


def _random_augment_face_rgb(rgb: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """
    Stochastic **identity-preserving** chain: small geometry, lighting, sensor.

    No horizontal flip on aligned ArcFace crops.
    """
    out = rgb.astype(np.float32)

    h, w = out.shape[:2]
    center = (w * 0.5, h * 0.5)
    angle = float(rng.uniform(-5.5, 5.5))
    scale = float(rng.uniform(0.985, 1.015))
    m = cv2.getRotationMatrix2D(center, angle, scale)
    tx = float(rng.uniform(-2.2, 2.2))
    ty = float(rng.uniform(-2.2, 2.2))
    m[0, 2] += tx
    m[1, 2] += ty
    out_u8 = np.clip(out, 0, 255).astype(np.uint8)
    out_u8 = cv2.warpAffine(
        out_u8,
        m,
        (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT_101,
    )
    out = out_u8.astype(np.float32)

    out *= float(rng.uniform(0.92, 1.08))
    out = np.clip(out, 0, 255)

    if rng.random() > 0.25:
        per_ch = rng.uniform(0.97, 1.03, size=(1, 1, 3)).astype(np.float32)
        out *= per_ch
        out = np.clip(out, 0, 255)

    if rng.random() > 0.35:
        g = float(rng.uniform(0.94, 1.06))
        x = out / 255.0
        out = np.clip(np.power(np.clip(x, 1e-6, 1.0), g) * 255.0, 0, 255)

    if rng.random() > 0.42:
        mean = float(out.mean())
        out = (out - mean) * float(rng.uniform(0.92, 1.10)) + mean
        out = np.clip(out, 0, 255)

    out_u8 = out.astype(np.uint8)

    if rng.random() > 0.5:
        q = int(rng.integers(62, 90))
        bgr = cv2.cvtColor(out_u8, cv2.COLOR_RGB2BGR)
        ok, enc = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), q])
        if ok:
            dec = cv2.imdecode(enc, cv2.IMREAD_COLOR)
            if dec is not None:
                out_u8 = cv2.cvtColor(dec, cv2.COLOR_BGR2RGB)

    if rng.random() > 0.55:
        k = int(rng.choice([3, 3, 5]))
        sigma = float(rng.uniform(0.35, 1.05))
        out_u8 = cv2.GaussianBlur(out_u8, (k, k), sigmaX=sigma, sigmaY=sigma)

    if rng.random() > 0.5:
        std = float(rng.uniform(1.0, 3.2))
        noise = rng.normal(0.0, std, out_u8.shape).astype(np.float32)
        out_u8 = np.clip(out_u8.astype(np.float32) + noise, 0, 255).astype(np.uint8)

    if rng.random() > 0.62:
        hh, ww = out_u8.shape[:2]
        factor = float(rng.uniform(0.82, 0.94))
        nw = max(int(ww * factor), 96)
        nh = max(int(hh * factor), 96)
        small = cv2.resize(out_u8, (nw, nh), interpolation=cv2.INTER_AREA)
        out_u8 = cv2.resize(small, (ww, hh), interpolation=cv2.INTER_LINEAR)

    if rng.random() > 0.78:
        k = int(rng.integers(3, 6))
        if k % 2 == 0:
            k += 1
        kernel = np.zeros((k, k), np.float32)
        if rng.random() > 0.5:
            kernel[k // 2, :] = 1.0 / k
        else:
            kernel[:, k // 2] = 1.0 / k
        bgr = cv2.cvtColor(out_u8, cv2.COLOR_RGB2BGR)
        bgr = cv2.filter2D(bgr, -1, kernel)
        out_u8 = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

    return out_u8


def _default_augment_staff_queryset() -> QuerySet:
    return (
        models.Staff.objects.filter(needs_training=True)
        .exclude(avatar__isnull=True)
        .exclude(avatar="")
    )


def _save_augment_if_valid(
    augment_root: str,
    staff_pin: str,
    file_index: int,
    aug_rgb: np.ndarray,
    ext: str,
) -> Tuple[bool, int]:
    if not _validate_face_present_rgb(aug_rgb):
        return False, file_index
    path = os.path.join(augment_root, f"{staff_pin}_aug_{file_index:03d}{ext}")
    cv2.imwrite(path, cv2.cvtColor(aug_rgb, cv2.COLOR_RGB2BGR))
    logger.debug("Saved validated augment %s", path)
    return True, file_index + 1


def run_staff_avatar_augmentation(
    staff_queryset: Optional[QuerySet] = None,
) -> Dict[str, str]:
    """
    Augment **face crops** (not full-frame avatars) for staff with needs_training.

    Uses face-ID-oriented CPU augments (lighting, WB, JPEG, blur, mild geometry).
    Drops samples where ArcFace no longer detects a face.

    Returns a mapping PIN -> human-readable skip reason for staff who produced
    no augmented files (successful PINs are absent from the dict).
    """
    notes: Dict[str, str] = {}
    qs = (
        staff_queryset
        if staff_queryset is not None
        else _default_augment_staff_queryset()
    )
    if not qs.exists():
        logger.info(
            "No staff members found with a valid avatar and needs_training set to True."
        )
        return notes

    logger.info(
        "Face-ID augmentation: %s presets + up to %s random validated samples.",
        len(FACE_ID_PRESET_AUGMENTS),
        RANDOM_AUGMENTS_TARGET,
    )

    try:
        for staff_member in qs.iterator(chunk_size=50):
            pin = staff_member.pin
            avatar_path = os.path.join(settings.MEDIA_ROOT, staff_member.avatar.name)
            original_extension = os.path.splitext(avatar_path)[1]
            if not original_extension:
                original_extension = ".jpg"
            test_image = ml.imread_bgr(avatar_path)
            if test_image is None:
                notes[pin] = "не удалось прочитать файл аватара"
                logger.error(
                    "Failed to read image from %s for staff member %s",
                    avatar_path,
                    staff_member,
                )
                continue
            test_image_rgb = cv2.cvtColor(test_image, cv2.COLOR_BGR2RGB)
            logger.info(
                "Loaded image with shape %s from %s for staff member %s",
                test_image.shape,
                avatar_path,
                staff_member,
            )

            face_square: Optional[np.ndarray] = None
            aligned = insightface_aligned_face_rgb(test_image_rgb)
            if aligned is not None and _validate_face_present_rgb(aligned):
                face_square = aligned
                logger.info(
                    "Using ArcFace 5-point aligned crop for staff %s",
                    staff_member.pin,
                )
            if face_square is None:
                face_coords = get_face_bbox(test_image_rgb)
                if face_coords is None:
                    notes[pin] = "на исходном фото ArcFace не находит лицо"
                    logger.error(
                        "No face detected in the image %s for staff member %s",
                        avatar_path,
                        staff_member,
                    )
                    continue
                expanded = expand_face_bbox(
                    face_coords,
                    test_image_rgb.shape,
                    expand_ratio_left=0.1,
                    expand_ratio_right=0.1,
                    expand_ratio_top=0.1,
                    expand_ratio_bottom=0.2,
                )
                face_square = square_face_crop_rgb(
                    test_image_rgb,
                    expanded[0],
                    expanded[1],
                    expanded[2],
                    expanded[3],
                )
                if face_square is None:
                    notes[pin] = "не удалось вырезать квадрат лица"
                    logger.error("Face square crop failed for %s", staff_member)
                    continue
                if not _validate_face_present_rgb(face_square):
                    notes[pin] = "после кропа ArcFace не видит лицо"
                    logger.error("No face in square crop for %s", staff_member)
                    continue

            augment_root = str(settings.AUGMENT_ROOT).format(staff_pin=staff_member.pin)
            os.makedirs(augment_root, exist_ok=True)

            file_index = 0
            rng = np.random.default_rng(seed=hash(staff_member.pin) % (2**32))

            for _name, preset_fn in FACE_ID_PRESET_AUGMENTS.items():
                aug_rgb = preset_fn(np.copy(face_square))
                ok, file_index = _save_augment_if_valid(
                    augment_root,
                    staff_member.pin,
                    file_index,
                    aug_rgb,
                    original_extension,
                )
                if not ok:
                    logger.debug("Preset %s rejected (no face) for %s", _name, pin)

            saved_random = 0
            attempts = 0
            while (
                saved_random < RANDOM_AUGMENTS_TARGET
                and attempts < RANDOM_AUGMENT_MAX_ATTEMPTS
            ):
                attempts += 1
                aug_rgb = _random_augment_face_rgb(np.copy(face_square), rng)
                ok, file_index = _save_augment_if_valid(
                    augment_root,
                    staff_member.pin,
                    file_index,
                    aug_rgb,
                    original_extension,
                )
                if ok:
                    saved_random += 1

            if file_index == 0:
                notes[pin] = (
                    "базовый кроп принят, но каждый аугмент отклонён: "
                    "после преобразований ArcFace не находит лицо"
                )

            logger.info(
                "Staff %s: augmentations saved with last index %s (random ok=%s/%s attempts=%s)",
                staff_member.pin,
                file_index,
                saved_random,
                RANDOM_AUGMENTS_TARGET,
                attempts,
            )
    except Exception as e:
        logger.error("An error occurred during the augmentation process: %s", e)
        raise
    return notes


def run_dali_augmentation_for_all_staff() -> None:
    """Backward-compatible entrypoint: runs face-ID augmentation (CPU, no DALI)."""
    run_staff_avatar_augmentation()


def get_face_bbox(image_rgb: np.ndarray):
    try:
        ml.load_arcface_model()
        inst = ml.arcface_model_holder.instance
        if inst is None:
            logger.error("ArcFace model is not initialized.")
            return None
        if image_rgb.ndim == 3 and image_rgb.shape[2] == 3:
            face_input = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR)
        else:
            face_input = image_rgb
        faces = inst.get(face_input)
        if faces:
            face = faces[0]
            bbox = face.bbox.astype(int)
            x_min, y_min, x_max, y_max = bbox
            x_min = max(0, x_min)
            y_min = max(0, y_min)
            x_max = min(image_rgb.shape[1], x_max)
            y_max = min(image_rgb.shape[0], y_max)
            return x_min, y_min, x_max, y_max
        return None
    except Exception as e:
        logger.error("Ошибка при обнаружении лица: %s", e)
        return None


if __name__ == "__main__":
    run_dali_augmentation_for_all_staff()
