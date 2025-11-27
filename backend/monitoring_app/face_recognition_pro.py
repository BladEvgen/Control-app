"""
Professional Face Recognition System - Apple Face ID Level
Combines multiple models, anti-spoofing, and quality checks
"""

import importlib
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, cast

import numpy as np
import torch
from deepface import DeepFace
from insightface.app import FaceAnalysis
from mtcnn import MTCNN
from retinaface import RetinaFace
from scipy.spatial.distance import euclidean
from scipy.stats import entropy
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

cv2 = cast(Any, importlib.import_module("cv2"))


class SecurityLevel(Enum):
    """Security levels for face recognition"""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    ULTRA = 4


@dataclass
class FaceRecognitionResult:
    """Result of face recognition"""

    success: bool
    person_id: Optional[str]
    confidence: float
    liveness_score: float
    quality_score: float
    details: Dict[str, Any]
    warnings: List[str]


@dataclass
class FaceQualityMetrics:
    """Face quality assessment metrics"""

    sharpness: float
    brightness: float
    contrast: float
    symmetry: float
    pose_quality: float
    occlusion_score: float
    overall_quality: float


class MultiModelFaceRecognition:
    """
    Professional multi-model face recognition system
    Combines multiple state-of-the-art models for maximum accuracy
    """

    def __init__(self, security_level: SecurityLevel = SecurityLevel.MEDIUM):
        self.security_level = security_level
        self.models_loaded = False

        self.arcface_app = None
        self.mtcnn_detector = None
        self.retina_detector = None

        self.thresholds = self._get_thresholds()

        self._initialize_models()

    def _get_thresholds(self) -> Dict[str, float]:
        """Get thresholds based on security level"""
        thresholds = {
            SecurityLevel.LOW: {
                "similarity": 0.45,
                "liveness": 0.50,
                "quality": 0.50,
                "multi_model_agreement": 0.60,
            },
            SecurityLevel.MEDIUM: {
                "similarity": 0.55,
                "liveness": 0.65,
                "quality": 0.60,
                "multi_model_agreement": 0.70,
            },
            SecurityLevel.HIGH: {
                "similarity": 0.65,
                "liveness": 0.75,
                "quality": 0.70,
                "multi_model_agreement": 0.80,
            },
            SecurityLevel.ULTRA: {
                "similarity": 0.75,
                "liveness": 0.85,
                "quality": 0.80,
                "multi_model_agreement": 0.90,
            },
        }
        return thresholds[self.security_level]

    def _initialize_models(self):
        """Initialize all face recognition models with GPU/CPU fallback"""
        try:
            logger.info("Initializing face recognition models...")

            use_gpu: bool = torch.cuda.is_available()
            if use_gpu:
                logger.info("GPU detected - using CUDA acceleration")
            else:
                logger.info("No GPU detected - using CPU (slower)")

            try:
                providers = (
                    ["CUDAExecutionProvider", "CPUExecutionProvider"]
                    if use_gpu
                    else ["CPUExecutionProvider"]
                )
                self.arcface_app = FaceAnalysis(name="buffalo_l", providers=providers)
                ctx_id = 0 if use_gpu else -1
                self.arcface_app.prepare(ctx_id=ctx_id, det_size=(640, 640))
                logger.info("ArcFace model initialized successfully")
            except Exception as e:
                logger.warning(f"ArcFace GPU init failed, falling back to CPU: {e}")
                self.arcface_app = FaceAnalysis(
                    name="buffalo_l", providers=["CPUExecutionProvider"]
                )
                self.arcface_app.prepare(ctx_id=-1, det_size=(640, 640))

            try:
                device = "cuda:0" if use_gpu else "cpu"
                self.mtcnn_detector = MTCNN(device=device)
                logger.info(f"MTCNN initialized on {device}")
            except Exception as e:
                logger.warning(f"MTCNN GPU init failed, falling back to CPU: {e}")
                self.mtcnn_detector = MTCNN(device="cpu")

            self.models_loaded = True
            logger.info("All models initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize models: {e}")
            raise

    def recognize_face(
        self,
        image: np.ndarray,
        known_embeddings: Dict[str, Dict[str, np.ndarray]],
        previous_frame: Optional[np.ndarray] = None,
    ) -> FaceRecognitionResult:
        """
        Main face recognition pipeline

        Args:
            image: Input face image (BGR format)
            known_embeddings: Dictionary of {person_id: embedding_vector}
            previous_frame: Previous frame for liveness detection

        Returns:
            FaceRecognitionResult with all details
        """
        warnings = []

        try:
            quality_metrics = self.assess_face_quality(image)
            if quality_metrics.overall_quality < self.thresholds["quality"]:
                return FaceRecognitionResult(
                    success=False,
                    person_id=None,
                    confidence=0.0,
                    liveness_score=0.0,
                    quality_score=quality_metrics.overall_quality,
                    details={
                        "reason": "Poor image quality",
                        "metrics": quality_metrics,
                    },
                    warnings=["Image quality below threshold"],
                )

            faces = self.detect_faces_multimodel(image)
            if not faces:
                return FaceRecognitionResult(
                    success=False,
                    person_id=None,
                    confidence=0.0,
                    liveness_score=0.0,
                    quality_score=quality_metrics.overall_quality,
                    details={"reason": "No face detected"},
                    warnings=["No face found in image"],
                )

            best_face = max(faces, key=lambda x: x.get("confidence", 0))

            liveness_score = 0.0
            if self.security_level.value >= SecurityLevel.MEDIUM.value:
                liveness_score = self.check_liveness(image, previous_frame)
                if liveness_score < self.thresholds["liveness"]:
                    return FaceRecognitionResult(
                        success=False,
                        person_id=None,
                        confidence=0.0,
                        liveness_score=liveness_score,
                        quality_score=quality_metrics.overall_quality,
                        details={"reason": "Liveness check failed"},
                        warnings=["Possible spoofing attempt detected"],
                    )

            embeddings = self.extract_multi_model_embeddings(image, best_face)

            match_result = self.match_face(embeddings, known_embeddings)

            if self.security_level.value >= SecurityLevel.HIGH.value:
                agreement_score = self.check_model_agreement(embeddings, match_result)
                if agreement_score < self.thresholds["multi_model_agreement"]:
                    warnings.append("Low model agreement - uncertain match")

            return FaceRecognitionResult(
                success=match_result["success"],
                person_id=match_result.get("person_id"),
                confidence=match_result["confidence"],
                liveness_score=liveness_score,
                quality_score=quality_metrics.overall_quality,
                details={
                    "face_location": best_face.get("bbox"),
                    "embeddings_used": list(embeddings.keys()),
                    "match_details": match_result,
                },
                warnings=warnings,
            )

        except Exception as e:
            logger.error(f"Face recognition failed: {e}")
            return FaceRecognitionResult(
                success=False,
                person_id=None,
                confidence=0.0,
                liveness_score=0.0,
                quality_score=0.0,
                details={"error": str(e)},
                warnings=[f"Recognition error: {str(e)}"],
            )

    def assess_face_quality(self, image: np.ndarray) -> FaceQualityMetrics:
        """
        Comprehensive face quality assessment
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        sharpness = min(laplacian.var() / 500, 1.0)

        mean_brightness = np.mean(gray)
        brightness = 1.0 - abs(mean_brightness - 128) / 128

        contrast = min(gray.std() / 64, 1.0)

        _, w = gray.shape
        left_half = gray[:, : w // 2]
        right_half = cv2.flip(gray[:, w // 2 :], 1)
        min_width = min(left_half.shape[1], right_half.shape[1])
        symmetry_diff = np.mean(
            np.abs(
                left_half[:, :min_width].astype(float)
                - right_half[:, :min_width].astype(float)
            )
        )
        symmetry = max(0, 1 - symmetry_diff / 128)

        pose_quality = self._assess_pose_quality(image)

        occlusion_score = self._detect_occlusion(image)

        overall_quality = (
            sharpness * 0.25
            + brightness * 0.15
            + contrast * 0.15
            + symmetry * 0.15
            + pose_quality * 0.20
            + occlusion_score * 0.10
        )

        return FaceQualityMetrics(
            sharpness=float(sharpness),
            brightness=float(brightness),
            contrast=float(contrast),
            symmetry=float(symmetry),
            pose_quality=float(pose_quality),
            occlusion_score=float(occlusion_score),
            overall_quality=float(overall_quality),
        )

    def _assess_pose_quality(self, image: np.ndarray) -> float:
        """Assess if face pose is frontal"""
        try:
            result = self.mtcnn_detector.detect_faces(image)
            if not result:
                return 0.5

            landmarks = result[0]["keypoints"]

            left_eye = np.array(landmarks["left_eye"])
            right_eye = np.array(landmarks["right_eye"])
            nose = np.array(landmarks["nose"])

            eye_center = (left_eye + right_eye) / 2
            eye_distance = np.linalg.norm(right_eye - left_eye)

            nose_offset = abs(nose[0] - eye_center[0])
            horizontal_score = max(0, 1 - nose_offset / (eye_distance / 2))

            eye_angle = abs(
                np.arctan2(right_eye[1] - left_eye[1], right_eye[0] - left_eye[0])
            )
            vertical_score = max(0, 1 - eye_angle / (np.pi / 6))

            return float((horizontal_score + vertical_score) / 2)

        except Exception as e:
            logger.warning(f"Pose assessment failed: {e}")
            return 0.5

    def _detect_occlusion(self, image: np.ndarray) -> float:
        """Detect if face is occluded (mask, hand, etc.)"""
        try:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)

            h, w = edges.shape

            eye_region = edges[int(h * 0.3) : int(h * 0.5), :]
            nose_region = edges[
                int(h * 0.4) : int(h * 0.6), int(w * 0.35) : int(w * 0.65)
            ]
            mouth_region = edges[
                int(h * 0.6) : int(h * 0.8), int(w * 0.3) : int(w * 0.7)
            ]

            eye_density = np.sum(eye_region > 0) / eye_region.size
            nose_density = np.sum(nose_region > 0) / nose_region.size
            mouth_density = np.sum(mouth_region > 0) / mouth_region.size

            avg_density = (eye_density + nose_density + mouth_density) / 3

            if 0.05 <= avg_density <= 0.20:
                score = 1.0
            else:
                score = max(0, 1 - abs(avg_density - 0.125) / 0.125)

            return score

        except Exception as e:
            logger.warning(f"Occlusion detection failed: {e}")
            return 0.5

    def detect_faces_multimodel(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """
        Detect faces using multiple models for robustness
        """
        all_faces = []

        try:
            arcface_faces = self.arcface_app.get(image)
            for face in arcface_faces:
                all_faces.append(
                    {
                        "bbox": face.bbox.astype(int).tolist(),
                        "confidence": float(face.det_score),
                        "landmarks": (
                            face.kps.tolist() if hasattr(face, "kps") else None
                        ),
                        "source": "arcface",
                        "embedding": face.embedding,
                    }
                )
        except Exception as e:
            logger.warning(f"ArcFace detection failed: {e}")

        try:
            mtcnn_result = self.mtcnn_detector.detect_faces(image)
            mtcnn_faces = mtcnn_result if mtcnn_result is not None else []
            for face in mtcnn_faces:
                bbox = face["box"]
                all_faces.append(
                    {
                        "bbox": [
                            bbox[0],
                            bbox[1],
                            bbox[0] + bbox[2],
                            bbox[1] + bbox[3],
                        ],
                        "confidence": float(face["confidence"]),
                        "landmarks": face["keypoints"],
                        "source": "mtcnn",
                    }
                )
        except Exception as e:
            logger.warning(f"MTCNN detection failed: {e}")

        try:
            retina_faces = RetinaFace.detect_faces(image)
            if isinstance(retina_faces, dict):
                for _, face in retina_faces.items():
                    bbox = face["facial_area"]
                    all_faces.append(
                        {
                            "bbox": [
                                bbox[2],
                                bbox[3],
                                bbox[0],
                                bbox[1],
                            ],
                            "confidence": float(face["score"]),
                            "landmarks": face["landmarks"],
                            "source": "retinaface",
                        }
                    )
        except Exception as e:
            logger.warning(f"RetinaFace detection failed: {e}")

        merged_faces = self._merge_overlapping_faces(all_faces)

        return merged_faces

    def _merge_overlapping_faces(
        self, faces: List[Dict[str, Any]], iou_threshold: float = 0.5
    ) -> List[Dict[str, Any]]:
        """Merge overlapping face detections from different models"""
        if not faces:
            return []

        faces = sorted(faces, key=lambda x: x.get("confidence", 0), reverse=True)

        merged = []
        used = set()

        for i, face1 in enumerate(faces):
            if i in used:
                continue

            group = [face1]
            for j, face2 in enumerate(faces[i + 1 :], start=i + 1):
                if j in used:
                    continue

                iou = self._calculate_iou(face1["bbox"], face2["bbox"])
                if iou > iou_threshold:
                    group.append(face2)
                    used.add(j)

            best_face = max(group, key=lambda x: x.get("confidence", 0))
            best_face["detection_count"] = len(group)
            merged.append(best_face)

        return merged

    def _calculate_iou(self, bbox1: List[int], bbox2: List[int]) -> float:
        """Calculate Intersection over Union of two bounding boxes"""
        x1_min, y1_min, x1_max, y1_max = bbox1
        x2_min, y2_min, x2_max, y2_max = bbox2

        x_inter_min = max(x1_min, x2_min)
        y_inter_min = max(y1_min, y2_min)
        x_inter_max = min(x1_max, x2_max)
        y_inter_max = min(y1_max, y2_max)

        if x_inter_max < x_inter_min or y_inter_max < y_inter_min:
            return 0.0

        inter_area = (x_inter_max - x_inter_min) * (y_inter_max - y_inter_min)

        bbox1_area = (x1_max - x1_min) * (y1_max - y1_min)
        bbox2_area = (x2_max - x2_min) * (y2_max - y2_min)
        union_area = bbox1_area + bbox2_area - inter_area

        return inter_area / union_area if union_area > 0 else 0.0

    def check_liveness(
        self, image: np.ndarray, previous_frame: Optional[np.ndarray] = None
    ) -> float:
        """
        Advanced liveness detection combining multiple techniques
        """
        scores = []

        texture_score = self._check_texture_liveness(image)
        scores.append(("texture", texture_score, 0.25))

        frequency_score = self._check_frequency_liveness(image)
        scores.append(("frequency", frequency_score, 0.20))

        color_score = self._check_color_liveness(image)
        scores.append(("color", color_score, 0.20))

        depth_score = self._check_depth_liveness(image)
        scores.append(("depth", depth_score, 0.20))

        if previous_frame is not None:
            motion_score = self._check_motion_liveness(image, previous_frame)
            scores.append(("motion", motion_score, 0.15))

        total_weight = sum(weight for _, _, weight in scores)
        liveness_score = (
            sum(score * weight for _, score, weight in scores) / total_weight
        )

        logger.debug(f"Liveness scores: {[(name, score) for name, score, _ in scores]}")

        return liveness_score

    def _check_texture_liveness(self, image: np.ndarray) -> float:
        """Check texture patterns (real skin vs printed photo)"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        lbp = self._compute_lbp(gray)

        hist, _ = np.histogram(lbp.ravel(), bins=256, range=(0, 256))
        hist = hist.astype(float)
        hist /= hist.sum() + 1e-7

        lbp_entropy = float(entropy(hist + 1e-7))

        score = float(min(max((lbp_entropy - 4) / 4, 0.0), 1.0))

        return score

    def _compute_lbp(
        self, gray: np.ndarray, radius: int = 1, points: int = 8
    ) -> np.ndarray:
        """Compute Local Binary Pattern"""
        rows, cols = gray.shape
        lbp = np.zeros_like(gray, dtype=np.uint8)

        for i in range(radius, rows - radius):
            for j in range(radius, cols - radius):
                center = gray[i, j]
                binary_val = 0

                for point in range(points):
                    angle = 2 * np.pi * point / points
                    x = int(round(i + radius * np.cos(angle)))
                    y = int(round(j + radius * np.sin(angle)))

                    if 0 <= x < rows and 0 <= y < cols:
                        if gray[x, y] >= center:
                            binary_val |= 1 << point

                lbp[i, j] = binary_val

        return lbp

    def _check_frequency_liveness(self, image: np.ndarray) -> float:
        """Check frequency domain (photos have different frequency characteristics)"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        f_transform = np.fft.fft2(gray)
        f_shift = np.fft.fftshift(f_transform)
        magnitude = np.abs(f_shift)

        rows, cols = magnitude.shape
        crow, ccol = rows // 2, cols // 2

        mask = np.ones((rows, cols))
        r = 30
        y, x = np.ogrid[:rows, :cols]
        mask_area = (x - ccol) ** 2 + (y - crow) ** 2 <= r * r
        mask[mask_area] = 0

        high_freq_energy = np.sum(magnitude * mask)
        total_energy = np.sum(magnitude)

        score = float(min(high_freq_energy / (total_energy + 1e-7) * 10, 1.0))

        return score

    def _check_color_liveness(self, image: np.ndarray) -> float:
        """Check color distribution (real skin has specific color characteristics)"""
        ycbcr = cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb)

        cb = ycbcr[:, :, 1]
        cr = ycbcr[:, :, 2]

        cb_mean, cb_std = np.mean(cb), np.std(cb)
        cr_mean, cr_std = np.mean(cr), np.std(cr)

        cb_score = 1.0 if 77 <= cb_mean <= 127 else max(0, 1 - abs(cb_mean - 102) / 50)
        cr_score = 1.0 if 133 <= cr_mean <= 173 else max(0, 1 - abs(cr_mean - 153) / 50)

        std_score = float(min((cb_std + cr_std) / 40, 1.0))

        return float((cb_score + cr_score + std_score) / 3)

    def _check_depth_liveness(self, image: np.ndarray) -> float:
        """Estimate depth to detect 2D photos"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=5)
        sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=5)
        gradient_magnitude = np.sqrt(sobelx**2 + sobely**2)

        h, w = gradient_magnitude.shape
        regions = [
            gradient_magnitude[: h // 2, : w // 2],
            gradient_magnitude[: h // 2, w // 2 :],
            gradient_magnitude[h // 2 :, : w // 2],
            gradient_magnitude[h // 2 :, w // 2 :],
        ]

        region_means = [np.mean(region) for region in regions]
        depth_variance = float(np.var(region_means))

        score = float(min(depth_variance / 100, 1.0))

        return score

    def _check_motion_liveness(
        self, current: np.ndarray, previous: np.ndarray
    ) -> float:
        """Check motion patterns (real faces have natural micro-movements)"""
        gray_current = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
        gray_previous = cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY)

        if gray_current.shape != gray_previous.shape:
            gray_previous = cv2.resize(
                gray_previous, (gray_current.shape[1], gray_current.shape[0])
            )

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

        magnitude = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2)
        motion_mean = np.mean(magnitude)
        motion_std = np.std(magnitude)

        if motion_mean < 0.5:
            score = motion_mean / 0.5
        elif motion_mean > 5.0:
            score = float(max(0.0, 1.0 - (motion_mean - 5.0) / 5.0))
        else:
            variation_score = float(min(motion_std / 2.0, 1.0))
            score = float((1.0 + variation_score) / 2)

        return score

    def extract_multi_model_embeddings(
        self, image: np.ndarray, face_info: Dict[str, Any]
    ) -> Dict[str, np.ndarray]:
        """
        Extract embeddings using multiple models
        """
        embeddings = {}

        if "embedding" in face_info:
            embeddings["arcface"] = face_info["embedding"]
        else:
            try:
                arcface_faces = self.arcface_app.get(image)
                if arcface_faces:
                    embeddings["arcface"] = arcface_faces[0].embedding
            except Exception as e:
                logger.warning(f"ArcFace embedding extraction failed: {e}")

        try:
            vgg_embedding = DeepFace.represent(
                image,
                model_name="VGG-Face",
                enforce_detection=False,
                detector_backend="skip",
            )
            if vgg_embedding:
                embeddings["vggface"] = np.array(vgg_embedding[0]["embedding"])
        except Exception as e:
            logger.warning(f"VGG-Face embedding failed: {e}")

        try:
            facenet_embedding = DeepFace.represent(
                image,
                model_name="Facenet",
                enforce_detection=False,
                detector_backend="skip",
            )
            if facenet_embedding:
                embeddings["facenet"] = np.array(facenet_embedding[0]["embedding"])
        except Exception as e:
            logger.warning(f"Facenet embedding failed: {e}")

        try:
            facenet512_embedding = DeepFace.represent(
                image,
                model_name="Facenet512",
                enforce_detection=False,
                detector_backend="skip",
            )
            if facenet512_embedding:
                embeddings["facenet512"] = np.array(
                    facenet512_embedding[0]["embedding"]
                )
        except Exception as e:
            logger.warning(f"Facenet512 embedding failed: {e}")

        return embeddings

    def match_face(
        self,
        query_embeddings: Dict[str, np.ndarray],
        known_embeddings: Dict[str, Dict[str, np.ndarray]],
    ) -> Dict[str, Any]:
        """
        Match face against known embeddings using multiple models
        """
        if not query_embeddings or not known_embeddings:
            return {"success": False, "confidence": 0.0, "person_id": None}

        best_match = None
        best_confidence = 0.0
        model_scores = {}

        for person_id, person_embedding_dict in known_embeddings.items():
            person_scores = []

            for model_name, query_emb in query_embeddings.items():
                if model_name in person_embedding_dict:
                    person_emb = person_embedding_dict[model_name]

                    similarity = cosine_similarity(
                        query_emb.reshape(1, -1), person_emb.reshape(1, -1)
                    )[0][0]

                    distance = euclidean(query_emb, person_emb)
                    distance_score = 1 / (1 + distance)

                    combined_score = (similarity + distance_score) / 2
                    person_scores.append(combined_score)

                    model_scores[f"{person_id}_{model_name}"] = combined_score

            if person_scores:
                avg_score = np.mean(person_scores)

                if avg_score > best_confidence:
                    best_confidence = avg_score
                    best_match = person_id

        success = best_confidence >= self.thresholds["similarity"]

        return {
            "success": success,
            "person_id": best_match if success else None,
            "confidence": float(best_confidence),
            "model_scores": model_scores,
            "models_used": list(query_embeddings.keys()),
        }

    def check_model_agreement(
        self,
        _embeddings: Dict[str, np.ndarray],
        match_result: Dict[str, Any],
    ) -> float:
        """
        Check if multiple models agree on the match
        """
        if "model_scores" not in match_result:
            return 0.5

        model_scores = match_result["model_scores"]
        person_id = match_result.get("person_id")

        if not person_id:
            return 0.0

        person_scores = [
            score
            for key, score in model_scores.items()
            if key.startswith(f"{person_id}_")
        ]

        if not person_scores:
            return 0.0

        mean_score = float(np.mean(person_scores))
        std_score = float(np.std(person_scores))

        agreement = mean_score * (1 - min(std_score, 1.0))

        return float(agreement)


_face_recognition_system = None


def get_face_recognition_system(
    security_level: SecurityLevel = SecurityLevel.MEDIUM,
) -> MultiModelFaceRecognition:
    """Get or create face recognition system instance"""
    global _face_recognition_system

    if _face_recognition_system is None:
        _face_recognition_system = MultiModelFaceRecognition(security_level)

    return _face_recognition_system
