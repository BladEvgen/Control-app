import os
import logging

import cv2
from django.conf import settings
import numpy as np
import albumentations as A

from monitoring_app import models, ml

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def _build_albu_pipeline():
    return A.Compose(
        [
            A.HorizontalFlip(p=0.5),
            A.ColorJitter(brightness=0.1, contrast=0.1, saturation=0.1, hue=0.03, p=0.5),
            A.Affine(scale=(0.98, 1.02), rotate=(-10, 10), shear=(-3, 3), translate_percent=(0.0, 0.02), p=0.3),
            A.GaussianBlur(blur_limit=(3, 5), p=0.1),
            A.ImageCompression(quality_lower=80, quality_upper=95, p=0.2),
            A.RandomBrightnessContrast(brightness_limit=0.1, contrast_limit=0.1, p=0.3),
        ]
    )


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


def _is_quality_ok(face_bgr):
    try:
        min_size = getattr(settings, "FACE_MIN_SIZE_PX", 80)
        blur_thr = getattr(settings, "FACE_MIN_BLUR_VAR", 50.0)
        h, w = face_bgr.shape[:2]
        if min(h, w) < int(min_size):
            return False
        gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
        var_lap = cv2.Laplacian(gray, cv2.CV_64F).var()
        if var_lap < float(blur_thr):
            return False
        mean_val = float(np.mean(gray))
        if mean_val < 20 or mean_val > 235:
            return False
        return True
    except Exception:
        return False


def run_albu_augmentation_for_all_staff():
    try:
        staff_members = (
            models.Staff.objects.filter(needs_training=True)
            .exclude(avatar__isnull=True)
            .exclude(avatar="")
        )
        if not staff_members.exists():
            logger.info(
                "No staff members found with a valid avatar and needs_training set to True."
            )
            return
        for staff_member in staff_members:
            avatar_path = os.path.join(settings.MEDIA_ROOT, staff_member.avatar.name)
            original_extension = os.path.splitext(avatar_path)[1]
            test_image = cv2.imread(avatar_path, cv2.IMREAD_COLOR)
            if test_image is None:
                logger.error(
                    f"Failed to read image from {avatar_path} for staff member {staff_member}"
                )
                continue
            test_image_rgb = cv2.cvtColor(test_image, cv2.COLOR_BGR2RGB)
            logger.info(
                f"Loaded image with shape {test_image.shape} from {avatar_path} for staff member {staff_member}"
            )

            face_coords = get_face_bbox(test_image_rgb)
            if face_coords is None:
                logger.error(
                    f"No face detected in the image {avatar_path} for staff member {staff_member}"
                )
                continue
            expanded_face_coords = expand_face_bbox(
                face_coords,
                test_image_rgb.shape,
                expand_ratio_left=0.1,
                expand_ratio_right=0.1,
                expand_ratio_top=0.1,
                expand_ratio_bottom=0.2,
            )
            logger.info(f"Expanded face coordinates: {expanded_face_coords}")

            x_min, y_min, x_max, y_max = expanded_face_coords
            face_crop_bgr = test_image[y_min:y_max, x_min:x_max]
            if face_crop_bgr.size == 0:
                logger.warning("Empty crop encountered; skipping")
                continue
            # Align to 112x112 via ml alignment helper if possible
            try:
                from monitoring_app import ml as mlmod

                mlmod.load_arcface_model()
                faces = mlmod.arcface_model.get(test_image)
                if faces:
                    face = faces[0]
                    aligned = mlmod.align_face_with_landmarks(test_image, face.kps)
                    if aligned is not None:
                        face_crop_bgr = aligned
            except Exception:
                pass

            if not _is_quality_ok(face_crop_bgr):
                logger.warning("Base face crop failed quality gates; skipping")
                continue

            augmenter = _build_albu_pipeline()
            augment_root = str(settings.AUGMENT_ROOT).format(staff_pin=staff_member.pin)
            os.makedirs(augment_root, exist_ok=True)
            num_variants = int(getattr(settings, "MAX_AUG_VARIANTS", 12))
            saved = 0
            for i in range(num_variants):
                aug = augmenter(image=face_crop_bgr[:, :, ::-1])
                aug_img_rgb = aug["image"]
                aug_bgr = aug_img_rgb[:, :, ::-1]
                if not _is_quality_ok(aug_bgr):
                    continue
                # identity-consistency gate vs original aligned/crop
                try:
                    from monitoring_app import ml as mlmod
                    orig_emb = mlmod.create_face_encoding(face_crop_bgr)
                    aug_emb = mlmod.create_face_encoding(aug_bgr)
                    if orig_emb is None or aug_emb is None:
                        continue
                    orig_emb = np.asarray(orig_emb, dtype=np.float32)
                    aug_emb = np.asarray(aug_emb, dtype=np.float32)
                    orig_emb = orig_emb / (np.linalg.norm(orig_emb) + 1e-8)
                    aug_emb = aug_emb / (np.linalg.norm(aug_emb) + 1e-8)
                    sim = float(np.dot(orig_emb, aug_emb))
                    if sim < float(getattr(settings, "IDENTITY_GATE_THRESHOLD", 0.9)):
                        continue
                except Exception:
                    pass
                augmented_path = os.path.join(
                    augment_root,
                    f"{staff_member.pin}_augmented_{i + 1}{original_extension}",
                )
                cv2.imwrite(augmented_path, aug_bgr)
                saved += 1
            logger.info(f"Saved {saved}/{num_variants} augmented variants for {staff_member.pin}")
    except Exception as e:
        logger.error(f"An error occurred during the augmentation process: {e}")
        raise


def get_face_bbox(image):
    try:
        ml.load_arcface_model()
        faces = ml.arcface_model.get(image)
        if faces:
            face = faces[0]
            bbox = face.bbox.astype(int)
            x_min, y_min, x_max, y_max = bbox
            x_min = max(0, x_min)
            y_min = max(0, y_min)
            x_max = min(image.shape[1], x_max)
            y_max = min(image.shape[0], y_max)
            return x_min, y_min, x_max, y_max
        else:
            return None
    except Exception as e:
        logger.error(f"Ошибка при обнаружении лица: {e}")
        return None


if __name__ == "__main__":
    run_albu_augmentation_for_all_staff()
