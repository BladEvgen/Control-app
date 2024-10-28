import os
import cv2
import logging
import numpy as np
import nvidia.dali.fn as fn
from django.conf import settings
from monitoring_app import utils, models
from nvidia.dali.pipeline import pipeline_def
from nvidia.dali.auto_aug import augmentations
from nvidia.dali.auto_aug.core import signed_bin

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
    "posterize": lambda images: augmentations.posterize(
        images, magnitude_bin=signed_bin(1), num_magnitude_bins=10
    ),
}

def expand_face_bbox(
    face_coords, image_shape, expand_ratio_left=0.1, expand_ratio_right=0.1, expand_ratio_top=0.1, expand_ratio_bottom=0.2
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

def get_face_aware_augmentations(width, height, pad_top, pad_bottom, pad_left, pad_right):
    max_rotate_degree = 15

    padded_width = width + pad_left + pad_right
    padded_height = height + pad_top + pad_bottom

    max_shift_x = int(min(pad_left, pad_right) * 0.5)
    max_shift_y = int(min(pad_top, pad_bottom) * 0.5)

    shift_left_value = -int(max_shift_x * 1.5)  # Отрицательное значение для сдвига влево
    shift_down_value = int(max_shift_y * 0.10)   # Меньшее положительное значение для сдвига вниз


    logger.info(f"Shift values: shift_left={shift_left_value}, shift_down={shift_down_value}")

    def rotate_and_crop(images, angle):
        rotated = fn.rotate(images, angle=angle, fill_value=0, keep_size=False)
        crop_x = pad_left
        crop_y = pad_top
        crop_pos_x = crop_x / padded_width
        crop_pos_y = crop_y / padded_height
        cropped = fn.crop(rotated, crop=(width, height), crop_pos_x=crop_pos_x, crop_pos_y=crop_pos_y)
        return cropped

    def shift_and_crop(images, shift_x, shift_y):
        matrix = np.array([[1, 0, shift_x], [0, 1, shift_y]], dtype=np.float32)
        shifted = fn.warp_affine(images, matrix=matrix, size=(padded_width, padded_height))

        crop_x = pad_left - shift_x
        crop_y = pad_top - shift_y

        crop_x = max(0, min(crop_x, padded_width - width))
        crop_y = max(0, min(crop_y, padded_height - height))

        crop_pos_x = crop_x / padded_width
        crop_pos_y = crop_y / padded_height

        cropped = fn.crop(shifted, crop=(width, height), crop_pos_x=crop_pos_x, crop_pos_y=crop_pos_y)
        return cropped

    augmentations_dict = {
        "turn_left": lambda images: rotate_and_crop(images, angle=-max_rotate_degree),
        "turn_right": lambda images: rotate_and_crop(images, angle=max_rotate_degree),
        "shift_left": lambda images: shift_and_crop(images, shift_x=shift_left_value, shift_y=0),
        "shift_down": lambda images: shift_and_crop(images, shift_x=int(shift_left_value/2), shift_y=shift_down_value),
    }

    return augmentations_dict


@pipeline_def
def dali_augmentation_pipeline(image_data, width, height, pad_top, pad_bottom, pad_left, pad_right):
    images = fn.external_source(
        source=image_data, batch=True, device="gpu", layout="HWC"
    )

    static_aug_images = []
    for aug_name, aug_fn in static_augmentations_list.items():
        logger.info(f"Applying static augmentation: {aug_name}")
        static_aug_images.append(aug_fn(images))

    images_padded = fn.pad(
        images,
        fill_value=0,
        axes=(0, 1),
        shape=(height + pad_top + pad_bottom, width + pad_left + pad_right),
        align=8
    )

    augmentations_dict = get_face_aware_augmentations(width, height, pad_top, pad_bottom, pad_left, pad_right)
    face_aware_aug_images = []
    for aug_name, aug_fn in augmentations_dict.items():
        logger.info(f"Applying face-aware augmentation: {aug_name}")
        face_aware_aug_images.append(aug_fn(images_padded))

    aug_images = static_aug_images + face_aware_aug_images

    return tuple(aug_images)

def run_dali_augmentation_for_all_staff():
    try:
        staff_members = models.Staff.objects.filter(needs_training=True).exclude(avatar__isnull=True).exclude(avatar='')
        if not staff_members.exists():
            logger.info("No staff members found with a valid avatar and needs_training set to True.")
            return
        for staff_member in staff_members:
            avatar_path = os.path.join(settings.MEDIA_ROOT, staff_member.avatar.name)
            original_extension = os.path.splitext(avatar_path)[1]
            test_image = cv2.imread(avatar_path, cv2.IMREAD_COLOR)
            if test_image is None:
                logger.error(f"Failed to read image from {avatar_path} for staff member {staff_member}")
                continue
            test_image_rgb = cv2.cvtColor(test_image, cv2.COLOR_BGR2RGB)
            height, width = test_image.shape[:2]
            logger.info(f"Loaded image with shape {test_image.shape} from {avatar_path} for staff member {staff_member}")

            face_coords = get_face_bbox(test_image_rgb)
            if face_coords is None:
                logger.error(f"No face detected in the image {avatar_path} for staff member {staff_member}")
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

            face_width = expanded_face_coords[2] - expanded_face_coords[0]
            face_height = expanded_face_coords[3] - expanded_face_coords[1]
            pad_top = int(face_height * 0.5)
            pad_bottom = int(face_height * 0.5)
            pad_left = int(face_width * 0.5)
            pad_right = int(face_width * 0.5)

            def image_data():
                yield [test_image_rgb]

            pipe = dali_augmentation_pipeline(
                image_data, width, height, pad_top, pad_bottom, pad_left, pad_right,
                batch_size=1, num_threads=1, device_id=0
            )
            pipe.build()
            logger.info(f"Running DALI pipeline for staff member {staff_member}'s avatar image augmentation")
            augment_root = str(settings.AUGMENT_ROOT).format(staff_pin=staff_member.pin)
            os.makedirs(augment_root, exist_ok=True)
            output = pipe.run()
            for i, aug_output in enumerate(output):
                processed_images = aug_output.as_cpu().as_array()
                logger.info(f"Processing augmented image {i + 1} for staff member {staff_member}")
                aug_image = processed_images[0]
                augmented_path = os.path.join(
                    augment_root, f"{staff_member.pin}_augmented_{i + 1}{original_extension}"
                )
                cv2.imwrite(augmented_path, cv2.cvtColor(aug_image, cv2.COLOR_RGB2BGR))
                logger.info(f"Augmented image saved to: {augmented_path} for staff member {staff_member}")
    except Exception as e:
        logger.error(f"An error occurred during the augmentation process: {e}")
        raise

def get_face_bbox(image):
    try:
        utils.load_arcface_model()
        faces = utils.arcface_model.get(image)
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
