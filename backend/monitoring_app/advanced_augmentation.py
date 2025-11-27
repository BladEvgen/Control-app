"""
Advanced Augmentation for Robust Face Recognition
Handles variations in: lighting, makeup, glasses, hairstyle, aging, accessories
"""

import importlib
import logging
from typing import Any, List, Tuple, cast

import numpy as np

logger = logging.getLogger(__name__)

cv2 = cast(Any, importlib.import_module("cv2"))


class AdvancedFaceAugmentation:
    """
    Advanced augmentation techniques for face recognition robustness
    """

    def __init__(self):
        self.augmentation_methods = [
            "lighting_variation",
            "makeup_simulation",
            "glasses_overlay",
            "hair_occlusion",
            "aging_simulation",
            "expression_variation",
            "pose_variation",
            "accessory_overlay",
            "seasonal_variation",
        ]

    def augment_face(
        self, face_image: np.ndarray, num_variations: int = 20
    ) -> List[np.ndarray]:
        """
        Generate multiple augmented versions of face image

        Args:
            face_image: Original face image
            num_variations: Number of augmented images to generate

        Returns:
            List of augmented face images
        """
        augmented_images = [face_image.copy()]

        for _ in range(num_variations):
            img = face_image.copy()

            if np.random.random() > 0.3:
                img = self.vary_lighting(img)

            if np.random.random() > 0.5:
                img = self.simulate_makeup(img)

            if np.random.random() > 0.6:
                img = self.add_glasses(img)

            if np.random.random() > 0.7:
                img = self.add_hair_occlusion(img)

            if np.random.random() > 0.8:
                img = self.simulate_aging(img)

            if np.random.random() > 0.4:
                img = self.vary_expression(img)

            if np.random.random() > 0.5:
                img = self.add_noise(img)

            if np.random.random() > 0.6:
                img = self.vary_color_temperature(img)

            if np.random.random() > 0.7:
                img = self.add_accessories(img)

            augmented_images.append(img)

        return augmented_images

    def vary_lighting(self, image: np.ndarray) -> np.ndarray:
        """
        Simulate different lighting conditions
        - Directional lighting (left, right, top, bottom)
        - Ambient lighting changes
        - Shadow simulation
        """
        img = image.copy().astype(np.float32)

        direction = np.random.choice(["left", "right", "top", "bottom", "center"])

        h, w = img.shape[:2]
        lighting_map = np.ones((h, w), dtype=np.float32)

        if direction == "left":
            for i in range(w):
                lighting_map[:, i] = 0.4 + 0.6 * (i / w)
        elif direction == "right":
            for i in range(w):
                lighting_map[:, i] = 1.0 - 0.6 * (i / w)
        elif direction == "top":
            for i in range(h):
                lighting_map[i, :] = 0.4 + 0.6 * (i / h)
        elif direction == "bottom":
            for i in range(h):
                lighting_map[i, :] = 1.0 - 0.6 * (i / h)

        for c in range(3):
            img[:, :, c] *= lighting_map

        ambient = np.random.uniform(0.7, 1.3)
        img *= ambient

        img = np.clip(img, 0, 255).astype(np.uint8)
        return img

    def simulate_makeup(self, image: np.ndarray) -> np.ndarray:
        """
        Simulate makeup application
        - Lipstick (red/pink tones on lips area)
        - Eye makeup (darker around eyes)
        - Foundation (smoother skin tone)
        """
        img = image.copy()

        h, w = img.shape[:2]

        lip_region = img[int(h * 0.65) : int(h * 0.85), int(w * 0.35) : int(w * 0.65)]
        if lip_region.size > 0:
            lip_region[:, :, 2] = np.clip(lip_region[:, :, 2] * 1.3, 0, 255)
            lip_region[:, :, 0] = np.clip(lip_region[:, :, 0] * 0.9, 0, 255)
            img[int(h * 0.65) : int(h * 0.85), int(w * 0.35) : int(w * 0.65)] = (
                lip_region
            )

        eye_region = img[int(h * 0.25) : int(h * 0.45), int(w * 0.2) : int(w * 0.8)]
        if eye_region.size > 0:
            eye_region = (eye_region * 0.8).astype(np.uint8)
            img[int(h * 0.25) : int(h * 0.45), int(w * 0.2) : int(w * 0.8)] = eye_region

        img = cv2.bilateralFilter(img, 9, 75, 75)

        return img

    def add_glasses(self, image: np.ndarray) -> np.ndarray:
        """
        Overlay glasses on face
        - Different styles: regular, sunglasses, reading glasses
        - Different colors and opacity
        """
        img = image.copy()
        h, w = img.shape[:2]

        glasses_color = np.random.choice(
            [(0, 0, 0), (50, 50, 50), (100, 50, 20), (20, 20, 80)]
        )

        cv2.ellipse(
            img,
            (int(w * 0.35), int(h * 0.4)),
            (int(w * 0.08), int(h * 0.06)),
            0,
            0,
            360,
            tuple(int(c) for c in glasses_color),
            2,
        )
        cv2.ellipse(
            img,
            (int(w * 0.65), int(h * 0.4)),
            (int(w * 0.08), int(h * 0.06)),
            0,
            0,
            360,
            tuple(int(c) for c in glasses_color),
            2,
        )
        cv2.line(
            img,
            (int(w * 0.43), int(h * 0.4)),
            (int(w * 0.57), int(h * 0.4)),
            tuple(int(c) for c in glasses_color),
            2,
        )

        if np.random.random() > 0.5:
            mask = np.zeros((h, w), dtype=np.uint8)
            cv2.ellipse(
                mask,
                (int(w * 0.35), int(h * 0.4)),
                (int(w * 0.08), int(h * 0.06)),
                0,
                0,
                360,
                (255,),
                -1,
            )
            img[mask > 0] = (img[mask > 0] * 0.5).astype(np.uint8)

            mask = np.zeros((h, w), dtype=np.uint8)
            cv2.ellipse(
                mask,
                (int(w * 0.65), int(h * 0.4)),
                (int(w * 0.08), int(h * 0.06)),
                0,
                0,
                360,
                (255,),
                -1,
            )
            img[mask > 0] = (img[mask > 0] * 0.5).astype(np.uint8)

        return img

    def add_hair_occlusion(self, image: np.ndarray) -> np.ndarray:
        """
        Simulate hair partially covering face
        - Bangs covering forehead
        - Side hair covering cheeks
        - Different hair colors
        """
        img = image.copy()
        h, w = img.shape[:2]

        hair_color = np.random.choice(
            [
                (20, 20, 20),
                (40, 30, 20),
                (80, 60, 40),
                (150, 130, 100),
                (80, 40, 30),
            ]
        )

        if np.random.random() > 0.5:
            for i in range(int(h * 0.3)):
                wave = int(np.sin(i * 0.3) * 20)
                start_x = max(0, int(w * 0.2) + wave)
                end_x = min(w, int(w * 0.8) + wave)
                alpha = np.random.uniform(0.3, 0.8)
                img[i, start_x:end_x] = (
                    img[i, start_x:end_x] * (1 - alpha) + np.array(hair_color) * alpha
                ).astype(np.uint8)

        side = np.random.choice(["left", "right"])
        if side == "left":
            for i in range(int(h * 0.2), int(h * 0.7)):
                width = int(w * 0.15 * (1 - abs(i - h * 0.45) / (h * 0.25)))
                alpha = np.random.uniform(0.4, 0.9)
                img[i, :width] = (
                    img[i, :width] * (1 - alpha) + np.array(hair_color) * alpha
                ).astype(np.uint8)
        else:
            for i in range(int(h * 0.2), int(h * 0.7)):
                width = int(w * 0.15 * (1 - abs(i - h * 0.45) / (h * 0.25)))
                alpha = np.random.uniform(0.4, 0.9)
                img[i, -width:] = (
                    img[i, -width:] * (1 - alpha) + np.array(hair_color) * alpha
                ).astype(np.uint8)

        return img

    def simulate_aging(self, image: np.ndarray) -> np.ndarray:
        """
        Simulate aging effects
        - Wrinkles
        - Skin texture changes
        - Slight sagging
        """
        img = image.copy()

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        kernel = np.ones((3, 3), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=1)

        for c in range(3):
            img[:, :, c] = np.where(
                edges > 0, np.clip(img[:, :, c] - 20, 0, 255), img[:, :, c]
            )

        noise = np.random.randint(-10, 10, img.shape, dtype=np.int16)
        img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        img[:, :, 0] = np.clip(img[:, :, 0] * 0.95, 0, 255)
        img[:, :, 1] = np.clip(img[:, :, 1] * 1.05, 0, 255)
        img[:, :, 2] = np.clip(img[:, :, 2] * 1.05, 0, 255)

        return img

    def vary_expression(self, image: np.ndarray) -> np.ndarray:
        """
        Simulate different facial expressions
        - Smile
        - Neutral
        - Slight frown
        Note: This is simplified - in production use facial landmark manipulation
        """
        img = image.copy()
        h, _ = img.shape[:2]

        expression_type = np.random.choice(["smile", "neutral", "serious"])

        if expression_type == "smile":
            mouth_region = img[int(h * 0.65) : int(h * 0.85), :]
            if mouth_region.size > 0:
                mouth_region = cv2.convertScaleAbs(mouth_region, alpha=1.1, beta=5)
                img[int(h * 0.65) : int(h * 0.85), :] = mouth_region

        return img

    def add_noise(self, image: np.ndarray) -> np.ndarray:
        """
        Add various types of noise
        - Gaussian noise
        - Salt and pepper
        - ISO noise
        """
        img = image.copy().astype(np.float32)

        noise_type = np.random.choice(["gaussian", "salt_pepper", "iso"])

        if noise_type == "gaussian":
            noise = np.random.normal(0, np.random.uniform(5, 15), img.shape)
            img += noise
        elif noise_type == "salt_pepper":
            prob = np.random.uniform(0.01, 0.05)
            mask = np.random.random(img.shape[:2])
            img[mask < prob / 2] = 0
            img[mask > 1 - prob / 2] = 255
        else:
            scale = np.random.uniform(10, 30)
            noise = np.random.poisson(img / 255.0 * scale) / scale * 255.0 - img
            img += noise

        img = np.clip(img, 0, 255).astype(np.uint8)
        return img

    def vary_color_temperature(self, image: np.ndarray) -> np.ndarray:
        """
        Vary color temperature (warm/cool lighting)
        """
        img = image.copy().astype(np.float32)

        temperature = np.random.uniform(-30, 30)

        if temperature > 0:
            img[:, :, 2] += temperature
            img[:, :, 1] += temperature * 0.5
        else:
            img[:, :, 0] += abs(temperature)
            img[:, :, 1] += abs(temperature) * 0.3

        img = np.clip(img, 0, 255).astype(np.uint8)
        return img

    def add_accessories(self, image: np.ndarray) -> np.ndarray:
        """
        Add accessories like hats, scarves, earrings
        """
        img = image.copy()
        h, w = img.shape[:2]

        accessory = np.random.choice(["hat", "scarf", "earrings", "none"])

        if accessory == "hat":
            hat_color = tuple(np.random.randint(0, 255, 3).tolist())
            cv2.rectangle(
                img,
                (int(w * 0.2), 0),
                (int(w * 0.8), int(h * 0.15)),
                hat_color,
                -1,
            )

        elif accessory == "scarf":
            scarf_color = tuple(np.random.randint(0, 255, 3).tolist())
            cv2.rectangle(
                img,
                (0, int(h * 0.85)),
                (w, h),
                scarf_color,
                -1,
            )

        elif accessory == "earrings":
            earring_color = tuple(np.random.randint(100, 255, 3).tolist())
            cv2.circle(img, (int(w * 0.2), int(h * 0.5)), 5, earring_color, -1)
            cv2.circle(img, (int(w * 0.8), int(h * 0.5)), 5, earring_color, -1)

        return img


class QualityAssessment:
    """
    Assess image quality before recognition
    """

    def __init__(self):
        self.min_blur_threshold = 100
        self.min_brightness = 50
        self.max_brightness = 200

    def assess_quality(self, image: np.ndarray) -> Tuple[bool, float, dict]:
        """
        Assess if image quality is sufficient for recognition

        Returns:
            (is_acceptable, quality_score, details)
        """
        scores = {}

        blur_score = self._assess_blur(image)
        scores["blur"] = blur_score

        brightness_score = self._assess_brightness(image)
        scores["brightness"] = brightness_score

        contrast_score = self._assess_contrast(image)
        scores["contrast"] = contrast_score

        resolution_score = self._assess_resolution(image)
        scores["resolution"] = resolution_score

        quality_score = float(np.mean(list(scores.values())))
        is_acceptable = quality_score > 0.6

        return is_acceptable, quality_score, scores

    def _assess_blur(self, image: np.ndarray) -> float:
        """Assess image blur using Laplacian variance"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()

        score = min(laplacian_var / self.min_blur_threshold, 1.0)
        return score

    def _assess_brightness(self, image: np.ndarray) -> float:
        """Assess if brightness is in acceptable range"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        mean_brightness = np.mean(gray)

        if self.min_brightness <= mean_brightness <= self.max_brightness:
            score = 1.0
        else:
            if mean_brightness < self.min_brightness:
                score = mean_brightness / self.min_brightness
            else:
                score = max(0, 1 - (mean_brightness - self.max_brightness) / 55)

        return score

    def _assess_contrast(self, image: np.ndarray) -> float:
        """Assess image contrast"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        contrast = gray.std()

        score = float(min(contrast / 40, 1.0))
        return score

    def _assess_resolution(self, image: np.ndarray) -> float:
        """Assess if resolution is sufficient"""
        h, w = image.shape[:2]
        min_dimension = min(h, w)

        if min_dimension >= 112:
            score = 1.0
        else:
            score = min_dimension / 112

        return score
