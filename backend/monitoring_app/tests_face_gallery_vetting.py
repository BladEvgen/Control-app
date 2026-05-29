import tempfile
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import numpy as np
from django.test import SimpleTestCase, override_settings

from monitoring_app import ml
from monitoring_app.management.commands.build_staff_gallery_real import (
    _compact_gallery_report_for_disk,
)


def _unit(values: list[float]) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64)
    return arr / max(float(np.linalg.norm(arr)), 1e-10)


class FaceGalleryVettingTests(SimpleTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _file(self, name: str) -> str:
        path = self.root / name
        path.write_bytes(b"x")
        return str(path)

    def _run_vetting(
        self,
        sources: list[dict[str, object]],
        embeddings: dict[int, np.ndarray],
        metas: dict[int, dict[str, object]],
        pad_bad_ids: set[int] | None = None,
    ) -> tuple[list[list[float]], dict[str, object]]:
        ids_by_path = {
            str(Path(str(src["path"])).resolve()): i + 1
            for i, src in enumerate(sources)
        }
        pad_bad_ids = pad_bad_ids or set()

        def fake_imread(path: str) -> np.ndarray:
            img = np.zeros((32, 32, 3), dtype=np.uint8)
            img[0, 0, 0] = ids_by_path[str(Path(path).resolve())]
            return img

        def fake_encoding(
            image_bgr: np.ndarray,
            *,
            use_tta: bool | None = None,
        ) -> tuple[list[float], dict[str, object]]:
            _ = use_tta
            idx = int(image_bgr[0, 0, 0])
            return embeddings[idx].tolist(), metas[idx]

        def fake_pad(
            image_bgr: np.ndarray,
            *,
            trusted_source: bool = False,
        ) -> tuple[list[str], dict[str, object]]:
            _ = trusted_source
            idx = int(image_bgr[0, 0, 0])
            if idx in pad_bad_ids:
                return ["gallery_pad_suspicious"], {"pad_status": "suspicious"}
            return [], {
                "pad_status": "clean",
                "pad_trust_confirmed": True,
                "pad_risk_score": 0.01,
            }

        with (
            patch.object(ml, "imread_bgr", side_effect=fake_imread),
            patch.object(ml, "preprocess_image", side_effect=lambda img: img),
            patch.object(
                ml,
                "create_face_encoding_with_probe_meta",
                side_effect=fake_encoding,
            ),
            patch.object(ml, "_gallery_pad_reject_reasons", side_effect=fake_pad),
        ):
            return ml.create_vetted_gallery_embeddings_from_images(
                sources,
                use_tta=True,
                run_pad=True,
            )

    def _good_meta(self) -> dict[str, object]:
        return {
            "face_present": True,
            "det_score": 0.88,
            "face_area_ratio": 0.05,
            "blur_laplacian_var": 90.0,
            "brightness_mean": 128.0,
            "pose_yaw": 2.0,
            "pose_pitch": 1.0,
        }

    @override_settings(
        FACE_GALLERY_ATTENDANCE_MIN_ANCHOR_COS=0.54,
        FACE_GALLERY_ENROLLMENT_MIN_CENTROID_COS=0.0,
        FACE_GALLERY_REAL_DEDUPE_MAX_COS=0.9999,
    )
    def test_accepts_clean_attendance_and_rejects_pad_suspicious(self) -> None:
        avatar = self._file("avatar.jpg")
        attendance = self._file("attendance.jpg")
        spoof = self._file("spoof.jpg")
        sources = [
            {"path": avatar, "source": "avatar", "trusted": True},
            {"path": attendance, "source": "lesson_attendance", "trusted": False},
            {"path": spoof, "source": "lesson_attendance", "trusted": False},
        ]
        vec_avatar = _unit([1.0, 0.0, 0.0, 0.0])
        vec_attendance = _unit([0.84, 0.54, 0.0, 0.0])
        vectors = {1: vec_avatar, 2: vec_attendance, 3: vec_avatar}
        metas = {1: self._good_meta(), 2: self._good_meta(), 3: self._good_meta()}

        rows, report = self._run_vetting(sources, vectors, metas, pad_bad_ids={3})

        self.assertEqual(len(rows), 2)
        self.assertEqual(
            report["accepted_by_source"], {"avatar": 1, "lesson_attendance": 1}
        )
        self.assertEqual(report["rejected_by_reason"], {"gallery_pad_suspicious": 1})

    @override_settings(
        FACE_GALLERY_ATTENDANCE_MIN_ANCHOR_COS=0.70,
        FACE_GALLERY_ENROLLMENT_MIN_CENTROID_COS=0.0,
        FACE_GALLERY_REAL_DEDUPE_MAX_COS=0.9999,
    )
    def test_rejects_attendance_embedding_that_does_not_match_anchor(self) -> None:
        avatar = self._file("avatar.jpg")
        wrong = self._file("wrong.jpg")
        sources = [
            {"path": avatar, "source": "avatar", "trusted": True},
            {"path": wrong, "source": "lesson_attendance", "trusted": False},
        ]
        vectors = {
            1: _unit([1.0, 0.0, 0.0, 0.0]),
            2: _unit([0.2, 0.98, 0.0, 0.0]),
        }
        metas = {1: self._good_meta(), 2: self._good_meta()}

        rows, report = self._run_vetting(sources, vectors, metas)

        self.assertEqual(len(rows), 1)
        self.assertEqual(report["accepted_by_source"], {"avatar": 1})
        self.assertEqual(report["rejected_by_reason"], {"gallery_anchor_mismatch": 1})

    @override_settings(FACE_GALLERY_ENROLLMENT_BLUR_MIN=20.0)
    def test_rejects_low_quality_face_even_when_pad_is_clean(self) -> None:
        avatar = self._file("avatar.jpg")
        sources = [{"path": avatar, "source": "avatar", "trusted": True}]
        vectors = {1: _unit([1.0, 0.0, 0.0, 0.0])}
        bad_meta = self._good_meta()
        bad_meta["blur_laplacian_var"] = 8.0
        metas = {1: bad_meta}

        rows, report = self._run_vetting(sources, vectors, metas)

        self.assertEqual(rows, [])
        self.assertEqual(report["rejected_by_reason"], {"gallery_blurry_face": 1})

    @override_settings(FACE_GALLERY_ATTENDANCE_MIN_NO_ANCHOR_COUNT=3)
    def test_rejects_single_attendance_frame_without_anchor(self) -> None:
        attendance = self._file("attendance.jpg")
        sources = [
            {"path": attendance, "source": "lesson_attendance", "trusted": False}
        ]
        vectors = {1: _unit([1.0, 0.0, 0.0, 0.0])}
        metas = {1: self._good_meta()}

        rows, report = self._run_vetting(sources, vectors, metas)

        self.assertEqual(rows, [])
        self.assertEqual(report["rejected_by_reason"], {"gallery_missing_anchor": 1})


class FaceGalleryReportCompactionTests(SimpleTestCase):
    @override_settings(
        FACE_GALLERY_REAL_META_ACCEPTED_DETAIL_LIMIT=1,
        FACE_GALLERY_REAL_META_REJECTED_DETAIL_LIMIT=1,
    )
    def test_disk_report_is_bounded_and_drops_verbose_pad_tags(self) -> None:
        report = {
            "input_count": 4,
            "decoded_candidate_count": 4,
            "accepted_count": 2,
            "rejected_count": 2,
            "accepted_by_source": {"avatar": 1, "lesson_attendance": 1},
            "rejected_by_reason": {"gallery_pad_suspicious": 2},
            "accepted": [
                {"path": "/a.jpg", "source": "avatar", "quality_rank": 1.0},
                {"path": "/b.jpg", "source": "lesson_attendance", "quality_rank": 0.8},
            ],
            "rejected": [
                {
                    "path": "/c.jpg",
                    "source": "lesson_attendance",
                    "reasons": ["gallery_pad_suspicious"],
                    "pad_tags": ["very", "long", "internal", "trace"],
                },
                {"path": "/d.jpg", "source": "lesson_attendance", "reasons": ["bad"]},
            ],
        }

        compact = _compact_gallery_report_for_disk(report)

        self.assertEqual(compact["accepted_detail_count"], 1)
        self.assertEqual(compact["rejected_detail_count"], 1)
        self.assertEqual(compact["accepted_detail_truncated"], 1)
        self.assertEqual(compact["rejected_detail_truncated"], 1)
        rejected = cast(list[Any], compact["rejected"])
        self.assertIsInstance(rejected, list)
        first_rejected = cast(dict[str, object], rejected[0])
        self.assertNotIn("pad_tags", first_rejected)
