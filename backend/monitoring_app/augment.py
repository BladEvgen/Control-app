import os
import logging

import cv2
import nvidia.dali.fn as fn
from django.conf import settings
from nvidia.dali.pipeline import pipeline_def
from nvidia.dali.auto_aug import augmentations
from nvidia.dali.auto_aug.core import signed_bin

from monitoring_app import models, ml

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

static_augmentations_list = {
    "brightness_dark": lambda images: augmentations.brightness(
        images, magnitude_bin=signed_bin(3), num_magnitude_bins=10
    ),
    "brightness_light": lambda images: augmentations.brightness(
        images, magnitude_bin=signed_bin(8), num_magnitude_bins=10
    ),
    "contrast": lambda images: augmentations.contrast(
        images, magnitude_bin=signed_bin(5), num_magnitude_bins=10
    ),
    "color": lambda images: augmentations.color(
        images, magnitude_bin=signed_bin(9), num_magnitude_bins=10
    ),
    "sharpness": lambda images: augmentations.sharpness(
        images, magnitude_bin=signed_bin(7), num_magnitude_bins=40
    ),
    "flip": lambda images: fn.flip(images, horizontal=1),
}


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


@pipeline_def
def dali_augmentation_pipeline(
    image_data,
):
    images = fn.external_source(
        source=image_data, batch=True, device="gpu", layout="HWC"
    )

    static_aug_images = []
    for aug_name, aug_fn in static_augmentations_list.items():
        logger.info(f"Applying static augmentation: {aug_name}")
        static_aug_images.append(aug_fn(images))

    return tuple(static_aug_images)


def run_dali_augmentation_for_all_staff():
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

            def image_data():
                yield [test_image_rgb]

            pipe = dali_augmentation_pipeline(
                image_data,
                batch_size=1,
                num_threads=1,
                device_id=0,
            )
            pipe.build()
            logger.info(
                f"Running DALI pipeline for staff member {staff_member}'s avatar image augmentation"
            )
            augment_root = str(settings.AUGMENT_ROOT).format(staff_pin=staff_member.pin)
            os.makedirs(augment_root, exist_ok=True)
            output = pipe.run()
            for i, aug_output in enumerate(output):
                processed_images = aug_output.as_cpu().as_array()
                logger.debug(
                    f"Processing augmented image {i + 1} for staff member {staff_member}"
                )
                aug_image = processed_images[0]
                augmented_path = os.path.join(
                    augment_root,
                    f"{staff_member.pin}_augmented_{i + 1}{original_extension}",
                )
                cv2.imwrite(augmented_path, cv2.cvtColor(aug_image, cv2.COLOR_RGB2BGR))
                logger.debug(
                    f"Augmented image saved to: {augmented_path} for staff member {staff_member}"
                )
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
    run_dali_augmentation_for_all_staff()
