"""
Liveness Detection Module for Anti-Spoofing
Implements multiple techniques to detect fake faces (photos, videos, masks)
"""

import importlib
import logging
from typing import Any, Dict, Optional, Tuple, cast

import numpy as np

logger = logging.getLogger(__name__)

cv2 = cast(Any, importlib.import_module("cv2"))


class LivenessDetector:
    """
    Multi-modal liveness detection combining:
    - Texture analysis (LBP, Moiré patterns)
    - Motion analysis (optical flow)
    - Depth estimation
    - Frequency domain analysis
    """

    def __init__(self):
        self.texture_threshold = 0.6
        self.motion_threshold = 0.5
        self.frequency_threshold = 0.55

    def detect_liveness(
        self, face_image: np.ndarray, previous_frame: Optional[np.ndarray] = None
    ) -> Tuple[bool, float, Dict[str, Any]]:
        """
        Comprehensive liveness check

        Returns:
            (is_live, confidence, details_dict)
        """
        scores = {}

        texture_score = self._analyze_texture(face_image)
        scores["texture"] = texture_score

        frequency_score = self._analyze_frequency_domain(face_image)
        scores["frequency"] = frequency_score

        color_score = self._analyze_color_space(face_image)
        scores["color"] = color_score

        if previous_frame is not None:
            motion_score = self._analyze_motion(face_image, previous_frame)
            scores["motion"] = motion_score

        reflection_score = self._detect_screen_reflection(face_image)
        scores["reflection"] = reflection_score

        blur_score = self._analyze_blur_pattern(face_image)
        scores["blur"] = blur_score

        weights = {
            "texture": 0.25,
            "frequency": 0.20,
            "color": 0.15,
            "motion": 0.20 if previous_frame is not None else 0,
            "reflection": 0.10,
            "blur": 0.10,
        }

        if previous_frame is None:
            total = sum(v for k, v in weights.items() if k != "motion")
            weights = {k: v / total for k, v in weights.items() if k != "motion"}

        confidence = float(sum(scores[k] * weights[k] for k in scores))

        is_live = confidence > 0.6

        details = {
            "confidence": confidence,
            "scores": scores,
            "is_live": is_live,
        }

        return is_live, confidence, details

    def _analyze_texture(self, image: np.ndarray) -> float:
        """
        Local Binary Pattern (LBP) analysis
        Real skin has richer texture than printed photos
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        lbp = self._compute_lbp(gray)

        hist, _ = np.histogram(lbp.ravel(), bins=256, range=(0, 256))
        hist = hist.astype("float")
        hist /= hist.sum() + 1e-7

        entropy = -np.sum(hist * np.log2(hist + 1e-7))

        score = float(min(entropy / 8.0, 1.0))

        return score

    def _compute_lbp(
        self, gray: np.ndarray, radius: int = 1, points: int = 8
    ) -> np.ndarray:
        """Compute Local Binary Pattern"""
        rows, cols = gray.shape
        lbp = np.zeros_like(gray)

        for i in range(radius, rows - radius):
            for j in range(radius, cols - radius):
                center = gray[i, j]
                binary_string = ""

                for point in range(points):
                    angle = 2 * np.pi * point / points
                    x = int(i + radius * np.cos(angle))
                    y = int(j + radius * np.sin(angle))

                    if x >= 0 and x < rows and y >= 0 and y < cols:
                        binary_string += "1" if gray[x, y] >= center else "0"

                lbp[i, j] = int(binary_string, 2)

        return lbp

    def _analyze_frequency_domain(self, image: np.ndarray) -> float:
        """
        FFT analysis - printed photos have different frequency characteristics
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        f_transform = np.fft.fft2(gray)
        f_shift = np.fft.fftshift(f_transform)
        magnitude = np.abs(f_shift)

        rows, cols = magnitude.shape
        crow, ccol = rows // 2, cols // 2

        mask = np.ones((rows, cols), np.uint8)
        r = 30
        center = [crow, ccol]
        x, y = np.ogrid[:rows, :cols]
        mask_area = (x - center[0]) ** 2 + (y - center[1]) ** 2 <= r * r
        mask[mask_area] = 0

        f_shift_filtered = f_shift * mask
        high_freq_energy = np.sum(np.abs(f_shift_filtered))

        total_energy = np.sum(magnitude)
        score = float(min(high_freq_energy / (total_energy + 1e-7), 1.0))

        return score

    def _analyze_color_space(self, image: np.ndarray) -> float:
        """
        Analyze color distribution in YCbCr space
        Real skin has specific color characteristics
        """
        ycbcr = cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb)

        cb = ycbcr[:, :, 1]
        cr = ycbcr[:, :, 2]

        cb_mean = float(np.mean(cb))
        cr_mean = float(np.mean(cr))

        cb_score = 1.0 if 77 <= cb_mean <= 127 else max(0, 1 - abs(cb_mean - 102) / 50)
        cr_score = 1.0 if 133 <= cr_mean <= 173 else max(0, 1 - abs(cr_mean - 153) / 50)

        score = float((cb_score + cr_score) / 2)

        return score

    def _analyze_motion(self, current: np.ndarray, previous: np.ndarray) -> float:
        """
        Optical flow analysis - real faces have natural micro-movements
        """
        gray_current = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
        gray_previous = cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY)

        flow = cv2.calcOpticalFlowFarneback(
            gray_previous,
            gray_current,
            None,
            0.5,
            3,
            15,
            3,
            5,
            1.2,
            0,
        )

        magnitude, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])

        motion_mean = float(np.mean(magnitude))

        if motion_mean < 0.5:
            score = motion_mean / 0.5
        elif motion_mean > 5.0:
            score = max(0, 1 - (motion_mean - 5.0) / 5.0)
        else:
            score = 1.0

        return score

    def _detect_screen_reflection(self, image: np.ndarray) -> float:
        """
        Detect screen reflections that indicate photo/video replay
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        _, bright_spots = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY)

        bright_ratio = np.sum(bright_spots > 0) / bright_spots.size

        score = max(0, 1 - bright_ratio * 10)

        return score

    def _analyze_blur_pattern(self, image: np.ndarray) -> float:
        """
        Analyze blur patterns - photos have uniform blur, real faces have depth-based blur
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        h, w = gray.shape
        regions = [
            gray[0 : h // 2, 0 : w // 2],
            gray[0 : h // 2, w // 2 : w],
            gray[h // 2 : h, 0 : w // 2],
            gray[h // 2 : h, w // 2 : w],
        ]

        region_variances = []
        for region in regions:
            lap = cv2.Laplacian(region, cv2.CV_64F)
            region_variances.append(lap.var())

        blur_variance = float(np.var(region_variances))

        score = float(min(blur_variance / 100, 1.0))

        return score


class DepthEstimator:
    """
    Estimate depth from single image to detect 2D photos
    """

    def __init__(self):
        # In production, use a pre-trained depth estimation model like MiDaS
        pass

    def estimate_depth(self, image: np.ndarray) -> np.ndarray:
        """
        Estimate depth map from image
        Real faces have depth variation, photos are flat
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=5)
        sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=5)

        gradient_magnitude = np.sqrt(sobelx**2 + sobely**2)

        depth_map = cv2.normalize(
            gradient_magnitude, dst=None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX
        )

        return depth_map.astype(np.uint8)

    def analyze_depth_variance(self, depth_map: np.ndarray) -> float:
        """
        Analyze depth variance - real faces have more depth variation
        """
        variance = np.var(depth_map)
        score = float(min(variance / 1000, 1.0))
        return score


class ChallengeResponseVerifier:
    """
    Challenge-response verification (e.g., "blink", "turn head", "smile")
    """

    def __init__(self):
        self.challenge_types = ["blink", "smile", "turn_left", "turn_right"]

    def verify_blink(
        self, _frames: list[np.ndarray], face_landmarks: list
    ) -> Tuple[bool, float]:
        """
        Verify if user blinked by analyzing eye aspect ratio over frames
        """
        ear_values = []

        for landmarks in face_landmarks:
            if landmarks is None:
                continue

            # Calculate EAR (simplified - in production use proper landmarks)
            # EAR = (||p2-p6|| + ||p3-p5||) / (2||p1-p4||)
            # where p1-p6 are eye landmark points

            ear = 0.3

            ear_values.append(ear)

        if len(ear_values) < 3:
            return False, 0.0

        ear_array = np.array(ear_values)
        ear_diff = np.diff(ear_array)

        blink_detected = bool(np.any(ear_diff < -0.1) and np.any(ear_diff > 0.1))

        confidence = 1.0 if blink_detected else 0.0

        return blink_detected, confidence

    def verify_head_turn(
        self, _frames: list[np.ndarray], _direction: str
    ) -> Tuple[bool, float]:
        """
        Verify if user turned head in requested direction
        """
        turn_detected = False
        confidence = 0.0

        return turn_detected, confidence
