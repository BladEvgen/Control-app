"""
Integration module for professional face recognition system
Replaces old ml.py functions with new pro system
"""

import importlib
import logging
import os
from typing import Any, Dict, List, Optional, Tuple, cast

import numpy as np
from django.conf import settings
from rest_framework.exceptions import ValidationError

cv2 = cast(Any, importlib.import_module("cv2"))

from monitoring_app import models
from monitoring_app.advanced_augmentation import (
    AdvancedFaceAugmentation,
    QualityAssessment,
)
from monitoring_app.face_recognition_pro import (
    FaceRecognitionResult,
    SecurityLevel,
    get_face_recognition_system,
)

logger = logging.getLogger(__name__)


class ProFaceRecognitionService:
    """
    Professional face recognition service
    Drop-in replacement for old ML functions
    """

    def __init__(self):
        self.recognition_system = get_face_recognition_system(SecurityLevel.MEDIUM)
        self.augmenter = AdvancedFaceAugmentation()
        self.quality_checker = QualityAssessment()

        self._embedding_cache = {}

    def create_embeddings_for_staff(self, staff: models.Staff) -> None:
        """
        Create embeddings for staff member using advanced augmentation

        Args:
            staff: Staff model instance

        Raises:
            ValueError: If avatar is missing or embeddings cannot be created
        """
        try:
            if not staff.avatar or not os.path.exists(staff.avatar.path):
                logger.error(f"Avatar missing for {staff.pin}")
                raise ValueError(f"Avatar missing for {staff.pin}")

            avatar_path = str(staff.avatar.path)
            logger.info(f"Creating embeddings for {staff.pin}")

            original_image = cv2.imread(avatar_path)
            if original_image is None:
                raise ValueError(f"Cannot read image: {avatar_path}")

            is_acceptable, quality_score, _ = self.quality_checker.assess_quality(
                original_image
            )
            if not is_acceptable:
                logger.warning(
                    f"Low quality image for {staff.pin}: {quality_score:.2f}"
                )

            augmented_images = self.augmenter.augment_face(
                original_image,
                num_variations=getattr(settings, "AUGMENTATION_VARIATIONS", 30),
            )

            logger.info(
                f"Generated {len(augmented_images)} augmented images for {staff.pin}"
            )

            augment_root = str(settings.AUGMENT_ROOT).format(staff_pin=staff.pin)
            os.makedirs(augment_root, exist_ok=True)

            augmented_paths = []
            for idx, aug_img in enumerate(augmented_images):
                aug_path = os.path.join(augment_root, f"{staff.pin}_aug_{idx}.jpg")
                cv2.imwrite(aug_path, aug_img)
                augmented_paths.append(aug_path)

            reference_embedding = self._compute_reference_arcface_embedding(
                original_image
            )
            external_faces: List[np.ndarray] = []
            if reference_embedding is not None:
                external_faces = self._collect_external_training_images(
                    staff, reference_embedding
                )

            if external_faces:
                external_dir = os.path.join(augment_root, "external")
                os.makedirs(external_dir, exist_ok=True)
                for idx, face_img in enumerate(external_faces):
                    ext_path = os.path.join(
                        external_dir, f"{staff.pin}_external_{idx}.jpg"
                    )
                    cv2.imwrite(ext_path, face_img)
                    augmented_paths.append(ext_path)
                logger.info(
                    f"Added {len(external_faces)} curated external photos for {staff.pin}"
                )

            all_embeddings = {
                "arcface": [],
                "vggface": [],
                "facenet": [],
                "facenet512": [],
            }

            for img_path in [avatar_path] + augmented_paths:
                img = cv2.imread(img_path)
                if img is None:
                    continue

                embeddings = self.recognition_system.extract_multi_model_embeddings(
                    img, {}
                )

                for model_name, embedding in embeddings.items():
                    if model_name in all_embeddings:
                        all_embeddings[model_name].append(embedding)

            final_embeddings = {}
            for model_name, emb_list in all_embeddings.items():
                if emb_list:
                    final_embeddings[model_name] = np.mean(emb_list, axis=0)

            embeddings_path = os.path.join(
                os.path.dirname(avatar_path), f"{staff.pin}_embeddings_pro.npz"
            )
            np.savez(embeddings_path, **final_embeddings)

            logger.info(
                f"Saved embeddings for {staff.pin} at {embeddings_path} "
                f"(models: {list(final_embeddings.keys())})"
            )

        except Exception as e:
            logger.error(f"Failed to create embeddings for {staff.pin}: {e}")
            raise

    def load_embeddings_for_staff(self, staff: models.Staff) -> Dict[str, np.ndarray]:
        """
        Load embeddings for staff member

        Args:
            staff: Staff model instance

        Returns:
            Dictionary of {model_name: embedding_array}
        """
        try:
            embeddings_path = os.path.join(
                os.path.dirname(staff.avatar.path), f"{staff.pin}_embeddings_pro.npz"
            )

            if not os.path.exists(embeddings_path):
                logger.info(f"Embeddings not found for {staff.pin}, creating...")
                self.create_embeddings_for_staff(staff)

            data = np.load(embeddings_path)
            embeddings = {key: data[key] for key in data.files}

            return embeddings

        except Exception as e:
            logger.error(f"Failed to load embeddings for {staff.pin}: {e}")
            return {}

    def load_all_known_embeddings(self) -> Dict[str, Dict[str, np.ndarray]]:
        """
        Load embeddings for all staff members

        Returns:
            Dictionary of {staff_pin: {model_name: embedding}}
        """
        known_embeddings = {}

        staff_members = models.Staff.objects.filter(avatar__isnull=False).exclude(
            avatar=""
        )

        for staff in staff_members:
            try:
                embeddings = self.load_embeddings_for_staff(staff)
                if embeddings:
                    known_embeddings[staff.pin] = embeddings
            except Exception as e:
                logger.warning(f"Could not load embeddings for {staff.pin}: {e}")

        logger.info(f"Loaded embeddings for {len(known_embeddings)} staff members")
        return known_embeddings

    def recognize_face_in_image(
        self,
        image_file,
        previous_frame: Optional[np.ndarray] = None,
        security_level: SecurityLevel = SecurityLevel.MEDIUM,
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Recognize faces in uploaded image

        Args:
            image_file: Uploaded image file
            previous_frame: Previous frame for liveness detection
            security_level: Security level to use

        Returns:
            (recognized_staff, unknown_faces)

        Raises:
            ValidationError: If recognition fails
        """
        try:
            file_bytes = np.frombuffer(image_file.read(), np.uint8)
            image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

            if image is None:
                raise ValidationError("Cannot read image")

            known_embeddings = self.load_all_known_embeddings()

            if not known_embeddings:
                raise ValidationError("No staff embeddings found in database")

            recognition_system = get_face_recognition_system(security_level)

            result: FaceRecognitionResult = recognition_system.recognize_face(
                image, known_embeddings, previous_frame
            )

            recognized_staff = []
            unknown_faces = []

            if result.success and result.person_id:
                try:
                    staff = models.Staff.objects.get(pin=result.person_id)

                    recognized_staff.append(
                        {
                            "pin": staff.pin,
                            "name": staff.name,
                            "surname": staff.surname,
                            "department": (
                                staff.department.name if staff.department else None
                            ),
                            "confidence": result.confidence,
                            "liveness_score": result.liveness_score,
                            "quality_score": result.quality_score,
                            "bbox": result.details.get("face_location"),
                            "security_level": security_level.name,
                        }
                    )

                    logger.info(
                        f"Recognized {staff.pin} with confidence {result.confidence:.2f}, "
                        f"liveness {result.liveness_score:.2f}"
                    )

                except models.Staff.DoesNotExist:
                    logger.warning(f"Staff with PIN {result.person_id} not found")
                    unknown_faces.append(
                        {
                            "status": "unknown",
                            "confidence": result.confidence,
                            "bbox": result.details.get("face_location"),
                        }
                    )
            else:
                unknown_faces.append(
                    {
                        "status": "unknown",
                        "reason": result.details.get("reason", "Not recognized"),
                        "confidence": result.confidence,
                        "liveness_score": result.liveness_score,
                        "quality_score": result.quality_score,
                        "warnings": result.warnings,
                        "bbox": result.details.get("face_location"),
                    }
                )

                logger.info(
                    f"Face not recognized: {result.details.get('reason')} "
                    f"(confidence: {result.confidence:.2f}, "
                    f"liveness: {result.liveness_score:.2f})"
                )

            return recognized_staff, unknown_faces

        except Exception as e:
            logger.error(f"Face recognition failed: {e}")
            raise ValidationError(f"Face recognition error: {str(e)}")

    def verify_face_match(
        self,
        image_file,
        staff_pin: str,
        security_level: SecurityLevel = SecurityLevel.HIGH,
    ) -> Tuple[bool, float, Dict]:
        """
        Verify if image matches specific staff member (1:1 verification)

        Args:
            image_file: Uploaded image file
            staff_pin: Staff PIN to verify against
            security_level: Security level to use

        Returns:
            (is_match, confidence, details)
        """
        try:
            file_bytes = np.frombuffer(image_file.read(), np.uint8)
            image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

            if image is None:
                return False, 0.0, {"error": "Cannot read image"}

            try:
                staff = models.Staff.objects.get(pin=staff_pin)
            except models.Staff.DoesNotExist:
                return False, 0.0, {"error": f"Staff {staff_pin} not found"}

            staff_embeddings = self.load_embeddings_for_staff(staff)
            if not staff_embeddings:
                return False, 0.0, {"error": "No embeddings found for staff"}

            known_embeddings = {staff_pin: staff_embeddings}

            recognition_system = get_face_recognition_system(security_level)

            result: FaceRecognitionResult = recognition_system.recognize_face(
                image, known_embeddings, None
            )

            is_match = result.success and result.person_id == staff_pin
            confidence = result.confidence

            details = {
                "liveness_score": result.liveness_score,
                "quality_score": result.quality_score,
                "warnings": result.warnings,
                "match_details": result.details,
            }

            return is_match, confidence, details

        except Exception as e:
            logger.error(f"Face verification failed: {e}")
            return False, 0.0, {"error": str(e)}

    def _compute_reference_arcface_embedding(
        self, image: np.ndarray
    ) -> Optional[np.ndarray]:
        """Compute a reference embedding from the staff avatar."""
        arcface_app = getattr(self.recognition_system, "arcface_app", None)
        if arcface_app is None:
            return None
        try:
            faces = arcface_app.get(image)
            if not faces:
                return None
            return faces[0].embedding
        except Exception as e:
            logger.warning(f"Failed to compute reference embedding: {e}")
            return None

    def _get_external_photo_dirs(self, staff: models.Staff) -> List[str]:
        """Return external directories for the staff member based on pin prefix."""
        upload_root = getattr(
            settings, "FACEID_UPLOAD_ROOT", "/var/www/kirill/faceid.medkrmu/uploads"
        )
        if not upload_root or not os.path.exists(upload_root):
            logger.debug(f"Upload root not found: {upload_root}")
            return []

        pin = (staff.pin or "").strip()
        if not pin:
            return []

        prefix = pin[0].upper()
        dirs: List[str] = []

        if prefix == "S":
            student_dir = os.path.join(upload_root, "students", pin)
            if os.path.isdir(student_dir):
                dirs.append(student_dir)
        elif prefix == "T":
            teacher_dirs = getattr(
                settings, "FACEID_TEACHER_SUBDIRS", ["teacher", "teachers"]
            )
            for subdir in teacher_dirs:
                teacher_dir = os.path.join(upload_root, subdir, pin)
                if os.path.isdir(teacher_dir):
                    dirs.append(teacher_dir)

        logger.debug(f"Found {len(dirs)} external directories for {staff.pin}: {dirs}")
        return dirs

    def _collect_external_training_images(
        self, staff: models.Staff, reference_embedding: np.ndarray
    ) -> List[np.ndarray]:
        """Collect curated faces from external directories."""
        photo_dirs = self._get_external_photo_dirs(staff)
        if not photo_dirs:
            logger.debug(f"No external photo directories found for {staff.pin}")
            return []

        similarity_threshold = getattr(
            settings,
            "FACEID_EXTERNAL_SIMILARITY_THRESHOLD",
            settings.FACE_RECOGNITION_PRO.get("SIMILARITY_THRESHOLD", 0.55),
        )
        max_images = getattr(settings, "FACEID_EXTERNAL_MAX_IMAGES", 200)
        collected: List[np.ndarray] = []

        logger.info(
            f"Collecting external images for {staff.pin} from {len(photo_dirs)} directories"
        )

        for directory in photo_dirs:
            try:
                if not os.path.exists(directory):
                    continue

                image_files = sorted(
                    [
                        f
                        for f in os.listdir(directory)
                        if f.lower().endswith((".jpg", ".jpeg", ".png"))
                    ]
                )

                logger.debug(
                    f"Found {len(image_files)} images in {directory} for {staff.pin}"
                )

                for filename in image_files:
                    if len(collected) >= max_images:
                        logger.info(
                            f"Reached max images limit ({max_images}) for {staff.pin}"
                        )
                        return collected

                    file_path = os.path.join(directory, filename)
                    try:
                        image = cv2.imread(file_path)
                        if image is None:
                            continue

                        is_acceptable, quality_score, quality_details = (
                            self.quality_checker.assess_quality(image)
                        )
                        if not is_acceptable or quality_score < 0.4:
                            logger.debug(
                                f"Skipping low quality image {filename}: {quality_score:.2f}"
                            )
                            continue

                        h, w = image.shape[:2]
                        if h < 200 or w < 200:
                            logger.debug(
                                f"Skipping too small image {filename}: {w}x{h}"
                            )
                            continue

                        match = self._select_matching_face(
                            image, reference_embedding, similarity_threshold
                        )
                        if match is None:
                            continue

                        cropped = self._crop_face(image, match["bbox"])
                        if cropped is None:
                            continue

                        is_acceptable_crop, quality_score_crop, _ = (
                            self.quality_checker.assess_quality(cropped)
                        )
                        min_quality = 0.45
                        if is_acceptable_crop and quality_score_crop >= min_quality:
                            collected.append(cropped)
                            logger.debug(
                                f"Added external image {filename} for {staff.pin} "
                                f"(similarity: {match['similarity']:.3f}, "
                                f"quality: {quality_score_crop:.2f}, "
                                f"combined_score: {match.get('combined_score', 0):.3f})"
                            )
                        else:
                            logger.debug(
                                f"Skipping cropped face from {filename}: "
                                f"quality too low ({quality_score_crop:.2f} < {min_quality})"
                            )

                    except Exception as e:
                        logger.warning(
                            f"Error processing {filename} for {staff.pin}: {e}"
                        )
                        continue

            except FileNotFoundError:
                logger.warning(f"Directory not found: {directory}")
                continue
            except Exception as e:
                logger.error(f"Error scanning directory {directory}: {e}")
                continue

        logger.info(
            f"Collected {len(collected)} external training images for {staff.pin} "
            f"from {len(photo_dirs)} directories "
            f"(threshold: {similarity_threshold:.2f}, max: {max_images})"
        )
        return collected

    def _select_matching_face(
        self,
        image: np.ndarray,
        reference_embedding: np.ndarray,
        threshold: float,
    ) -> Optional[Dict[str, Any]]:
        """
        Select the face in image that matches the reference (handles multiple faces).

        Handles cases where:
        - Multiple people in frame
        - People partially visible
        - People at different angles/distances
        - Need to find the one matching the original staff photo
        """
        arcface_app = getattr(self.recognition_system, "arcface_app", None)
        if arcface_app is None:
            return None

        try:
            faces = arcface_app.get(image)
            if not faces:
                return None

            ref_norm = reference_embedding / (
                np.linalg.norm(reference_embedding) + 1e-7
            )

            best_face: Optional[Dict[str, Any]] = None
            best_similarity = 0.0
            candidates: List[Dict[str, Any]] = []

            for face in faces:
                embedding = getattr(face, "embedding", None)
                bbox = getattr(face, "bbox", None)
                det_score = getattr(face, "det_score", 1.0)

                if embedding is None or bbox is None:
                    continue

                emb_norm = embedding / (np.linalg.norm(embedding) + 1e-7)

                similarity = float(np.dot(ref_norm, emb_norm))

                bbox_array = np.asarray(bbox, dtype=float)
                x_min, y_min, x_max, y_max = bbox_array
                face_width = x_max - x_min
                face_height = y_max - y_min
                face_area = face_width * face_height
                image_area = image.shape[0] * image.shape[1]
                size_ratio = face_area / image_area

                img_center_x = image.shape[1] / 2
                img_center_y = image.shape[0] / 2
                face_center_x = (x_min + x_max) / 2
                face_center_y = (y_min + y_max) / 2
                distance_from_center = np.sqrt(
                    (face_center_x - img_center_x) ** 2
                    + (face_center_y - img_center_y) ** 2
                )
                max_distance = np.sqrt(
                    (image.shape[1] / 2) ** 2 + (image.shape[0] / 2) ** 2
                )
                position_score = 1.0 - (distance_from_center / (max_distance + 1e-7))

                combined_score = (
                    similarity * 0.7
                    + float(det_score) * 0.1
                    + min(size_ratio * 10, 1.0) * 0.1
                    + position_score * 0.1
                )

                if similarity > threshold:
                    candidates.append(
                        {
                            "bbox": bbox,
                            "similarity": similarity,
                            "combined_score": combined_score,
                            "det_score": float(det_score),
                            "size_ratio": size_ratio,
                        }
                    )

            if not candidates:
                return None

            candidates.sort(key=lambda x: x["combined_score"], reverse=True)
            best_candidate = candidates[0]

            best_face = {
                "bbox": best_candidate["bbox"],
                "similarity": best_candidate["similarity"],
                "combined_score": best_candidate["combined_score"],
            }

            logger.debug(
                f"Selected face with similarity {best_candidate['similarity']:.3f}, "
                f"combined score {best_candidate['combined_score']:.3f}, "
                f"from {len(candidates)} candidates"
            )

            return best_face

        except Exception as e:
            logger.warning(f"Error detecting faces in external image: {e}")
            return None

    @staticmethod
    def _cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        v1 = np.asarray(vec1, dtype=float)
        v2 = np.asarray(vec2, dtype=float)
        denom = np.linalg.norm(v1) * np.linalg.norm(v2)
        if denom == 0:
            return 0.0
        return float(np.dot(v1, v2) / denom)

    @staticmethod
    def _crop_face(
        image: np.ndarray,
        bbox: Any,
        padding: float = 0.20,
    ) -> Optional[np.ndarray]:
        """
        Crop the detected face with optional padding.

        Handles partially visible faces by:
        - Using larger padding
        - Ensuring minimum size for recognition
        - Maintaining aspect ratio
        """
        if bbox is None:
            return None

        try:
            bbox_array = np.asarray(bbox, dtype=float)
            x_min, y_min, x_max, y_max = bbox_array.astype(int)

            width = x_max - x_min
            height = y_max - y_min
            if width <= 0 or height <= 0:
                return None

            face_size = min(width, height)
            adaptive_padding = padding * (1.0 + (112.0 / max(face_size, 1.0)))

            pad_x = int(width * adaptive_padding)
            pad_y = int(height * adaptive_padding)

            h, w = image.shape[:2]
            x1 = max(0, x_min - pad_x)
            y1 = max(0, y_min - pad_y)
            x2 = min(w, x_max + pad_x)
            y2 = min(h, y_max + pad_y)

            if x1 >= x2 or y1 >= y2:
                return None

            cropped = image[y1:y2, x1:x2]

            min_size = 112
            if cropped.shape[0] < min_size or cropped.shape[1] < min_size:
                scale = min_size / min(cropped.shape[0], cropped.shape[1])
                new_w = int(cropped.shape[1] * scale)
                new_h = int(cropped.shape[0] * scale)
                cropped = cv2.resize(
                    cropped, (new_w, new_h), interpolation=cv2.INTER_CUBIC
                )

            max_size = 640
            if cropped.shape[0] > max_size or cropped.shape[1] > max_size:
                scale = max_size / max(cropped.shape[0], cropped.shape[1])
                new_w = int(cropped.shape[1] * scale)
                new_h = int(cropped.shape[0] * scale)
                cropped = cv2.resize(
                    cropped, (new_w, new_h), interpolation=cv2.INTER_CUBIC
                )

            return cropped

        except Exception as e:
            logger.warning(f"Error cropping face: {e}")
            return None

    def batch_create_embeddings(self, staff_queryset=None) -> Dict[str, str]:
        """
        Create embeddings for multiple staff members

        Args:
            staff_queryset: QuerySet of staff members (default: all with avatars)

        Returns:
            Dictionary of {staff_pin: status}
        """
        if staff_queryset is None:
            staff_queryset = models.Staff.objects.filter(avatar__isnull=False).exclude(
                avatar=""
            )

        results = {}

        for staff in staff_queryset:
            try:
                self.create_embeddings_for_staff(staff)
                results[staff.pin] = "success"
                logger.info(f"✓ Created embeddings for {staff.pin}")
            except Exception as e:
                results[staff.pin] = f"failed: {str(e)}"
                logger.error(f"✗ Failed to create embeddings for {staff.pin}: {e}")

        return results


_pro_service = None


def get_pro_face_service() -> ProFaceRecognitionService:
    """Get or create professional face recognition service"""
    global _pro_service

    if _pro_service is None:
        _pro_service = ProFaceRecognitionService()

    return _pro_service


def recognize_faces_in_image(image_file):
    """
    Drop-in replacement for old recognize_faces_in_image function

    Args:
        image_file: Uploaded image file

    Returns:
        (recognized_staff, unknown_faces)
    """
    service = get_pro_face_service()
    return service.recognize_face_in_image(image_file)


def create_embeddings_for_staff(staff):
    """
    Drop-in replacement for old create_embeddings_for_staff function

    Args:
        staff: Staff model instance
    """
    service = get_pro_face_service()
    return service.create_embeddings_for_staff(staff)


def train_face_recognition_model(staff, **kwargs):
    """
    Drop-in replacement for old training function
    Now just creates embeddings (no separate model training needed)

    Args:
        staff: Staff model instance
    """
    service = get_pro_face_service()
    return service.create_embeddings_for_staff(staff)
