from __future__ import annotations

from django.test import SimpleTestCase, TestCase

from monitoring_app.face_verification_contract import (
    R_LIVENESS_FAILED,
    R_NEAREST_IMPOSTOR_TOO_CLOSE,
    R_PAD_PIPELINE_FAILED,
    R_PROBE_QUALITY_LOW,
    R_SCORE_BELOW_VERIFIED_THRESHOLD,
    R_WEAK_ENROLLMENT,
    LivenessPayload,
    QualityPayload,
)
from monitoring_app.face_verification_pad import pad_public_decision_from_result
from monitoring_app.face_verification_policy import decide_face_verify_binary
from monitoring_app.photo_pad import PadResult

_QUALITY_OK: QualityPayload = {
    "passed": True,
    "det_score": 0.9,
    "face_area_ratio": 0.12,
    "reason_codes": [],
}

_QUALITY_FAIL: QualityPayload = {
    "passed": False,
    "det_score": 0.1,
    "face_area_ratio": 0.001,
    "reason_codes": ["low_det_score"],
}


def _call(
    *,
    quality: QualityPayload,
    live: LivenessPayload,
    score: float,
    gallery_templates: int,
    thr_v: float = 0.76,
    identity_ambiguous: bool = False,
):
    return decide_face_verify_binary(
        **{
            "quality": quality,
            "liveness": live,
            "score": score,
            "gallery_templates": gallery_templates,
            "threshold": thr_v,
            "identity_ambiguous": identity_ambiguous,
        },
    )


class FaceVerifyPolicyPadMappingTests(SimpleTestCase):
    """PAD → binary decision: spoof vs pipeline error must not be conflated."""

    def test_suspicious_status_is_no_liveness_fail(self) -> None:
        live: LivenessPayload = {
            "checked": True,
            "status": "suspicious",
            "risk_score": 0.9,
            "model_version": "pad_v3",
            "tags": ["fasnet_fake"],
            "elapsed_ms": 10.0,
        }
        matched, fd, _summary, st, codes, _thr = _call(
            quality=_QUALITY_OK,
            live=live,
            score=0.99,
            gallery_templates=3,
        )
        self.assertFalse(matched)
        self.assertEqual(fd, "NO")
        self.assertEqual(st, "LIVENESS_FAIL")
        self.assertEqual(codes, [R_LIVENESS_FAILED])

    def _review_band(self, risk: float) -> LivenessPayload:
        return {
            "checked": True,
            "status": "review",
            "risk_score": risk,
            "model_version": "pad_clip_v2",
            "tags": [],
            "elapsed_ms": 10.0,
        }

    def test_review_band_is_no_whatever_the_probability(self) -> None:
        """No operator in Face Lab or face login: only a calibrated clean photo is live."""
        matched, fd, _s, st, _c, _t = _call(
            quality=_QUALITY_OK,
            live=self._review_band(0.06),
            score=0.99,
            gallery_templates=3,
        )
        self.assertEqual((matched, fd, st), (False, "NO", "LIVENESS_FAIL"))

        matched, fd, _s, st, codes, _t = _call(
            quality=_QUALITY_OK,
            live=self._review_band(0.97),
            score=0.99,
            gallery_templates=3,
        )
        self.assertEqual((matched, fd, st), (False, "NO", "LIVENESS_FAIL"))
        self.assertEqual(codes, [R_LIVENESS_FAILED])

    def test_pad_no_decision_is_hard_liveness_fail(self) -> None:
        live: LivenessPayload = {
            "checked": True,
            "decision": "NO",
            "status": "suspicious",
            "risk_score": 0.9,
            "model_version": "pad_v10",
            "tags": ["screen"],
            "elapsed_ms": 10.0,
        }
        matched, fd, _summary, st, codes, _thr = _call(
            quality=_QUALITY_OK,
            live=live,
            score=0.99,
            gallery_templates=3,
        )
        self.assertFalse(matched)
        self.assertEqual(fd, "NO")
        self.assertEqual(st, "LIVENESS_FAIL")
        self.assertEqual(codes, [R_LIVENESS_FAILED])

    def test_pad_error_status_is_pad_error(self) -> None:
        live: LivenessPayload = {
            "checked": True,
            "status": "error",
            "risk_score": 0.0,
            "model_version": "pad_v3",
            "tags": ["no_face"],
            "elapsed_ms": 5.0,
        }
        matched, fd, _summary, st, codes, _thr = _call(
            quality=_QUALITY_OK,
            live=live,
            score=0.99,
            gallery_templates=3,
        )
        self.assertFalse(matched)
        self.assertEqual(fd, "NO")
        self.assertEqual(st, "PAD_ERROR")
        self.assertEqual(codes, [R_PAD_PIPELINE_FAILED])

    def test_identity_ambiguous_rejects_even_high_score(self) -> None:
        live: LivenessPayload = {
            "checked": True,
            "status": "clean",
            "risk_score": 0.01,
            "model_version": "pad_v3",
            "tags": [],
            "elapsed_ms": 1.0,
        }
        matched, fd, summary, st, codes, thr_applied = _call(
            quality=_QUALITY_OK,
            live=live,
            score=0.94,
            gallery_templates=3,
            identity_ambiguous=True,
        )

        self.assertFalse(matched)
        self.assertEqual(fd, "NO")
        self.assertEqual(st, "REJECTED")
        self.assertIn(R_NEAREST_IMPOSTOR_TOO_CLOSE, codes)
        self.assertEqual(thr_applied, 0.0)
        self.assertEqual(summary, "Похоже на другого сотрудника.")

    def test_clean_status_without_trust_flag_allows_identity_match(self) -> None:
        live: LivenessPayload = {
            "checked": True,
            "status": "clean",
            "risk_score": 0.32,
            "model_version": "pad_v10",
            "tags": [],
            "elapsed_ms": 1.0,
        }
        matched, fd, summary, st, codes, thr_applied = _call(
            quality=_QUALITY_OK,
            live=live,
            score=0.82,
            gallery_templates=3,
            thr_v=0.76,
        )
        self.assertTrue(matched)
        self.assertEqual(fd, "YES")
        self.assertEqual(st, "VERIFIED")
        self.assertEqual(codes, [])
        self.assertAlmostEqual(thr_applied, 0.76)
        self.assertEqual(summary, "Да. Совпадение есть.")

    def test_zero_templates_is_no(self) -> None:
        live: LivenessPayload = {
            "checked": True,
            "status": "clean",
            "risk_score": 0.01,
            "model_version": "pad_v3",
            "tags": [],
            "elapsed_ms": 1.0,
        }
        matched, fd, _summary, st, codes, _thr = _call(
            quality=_QUALITY_OK,
            live=live,
            score=0.99,
            gallery_templates=0,
        )
        self.assertFalse(matched)
        self.assertEqual(fd, "NO")
        self.assertEqual(st, "REJECTED")
        self.assertIn(R_WEAK_ENROLLMENT, codes)

    def test_clean_photo_above_threshold_is_yes(self) -> None:
        live: LivenessPayload = {
            "checked": True,
            "status": "clean",
            "risk_score": 0.02,
            "model_version": "pad_v3",
            "tags": [],
            "elapsed_ms": 1.0,
        }
        matched, fd, _summary, st, codes, thr_applied = _call(
            quality=_QUALITY_OK,
            live=live,
            score=0.9,
            gallery_templates=3,
            thr_v=0.76,
        )
        self.assertTrue(matched)
        self.assertEqual(fd, "YES")
        self.assertEqual(st, "VERIFIED")
        self.assertEqual(codes, [])
        self.assertAlmostEqual(thr_applied, 0.76)

    def test_single_avatar_uses_the_one_threshold(self) -> None:
        """One photo is a full gallery: same threshold, no cold-start / weak tiers."""
        live: LivenessPayload = {"checked": True, "status": "clean"}
        yes = _call(
            quality=_QUALITY_OK,
            live=live,
            score=0.51,
            gallery_templates=1,
            thr_v=0.50,
        )
        self.assertEqual(yes[:2], (True, "YES"))
        self.assertAlmostEqual(yes[5], 0.50)
        no = _call(
            quality=_QUALITY_OK,
            live=live,
            score=0.49,
            gallery_templates=1,
            thr_v=0.50,
        )
        self.assertEqual(no[:2], (False, "NO"))
        self.assertEqual(no[4], [R_SCORE_BELOW_VERIFIED_THRESHOLD])

    def test_quality_fail_before_score_when_pad_clean(self) -> None:
        live: LivenessPayload = {
            "checked": True,
            "status": "clean",
            "risk_score": 0.01,
            "model_version": "pad_v3",
            "tags": [],
            "elapsed_ms": 1.0,
        }
        matched, fd, _summary, st, codes, _thr = _call(
            quality=_QUALITY_FAIL,
            live=live,
            score=0.99,
            gallery_templates=3,
        )
        self.assertFalse(matched)
        self.assertEqual(fd, "NO")
        self.assertEqual(st, "QUALITY_FAIL")
        self.assertEqual(codes[0], R_PROBE_QUALITY_LOW)


class FacePadPublicDecisionTests(SimpleTestCase):
    def test_only_clean_is_live(self) -> None:
        for status, expected in (
            ("clean", "YES"),
            ("review", "NO"),
            ("insufficient_input_review", "NO"),
            ("suspicious", "NO"),
            ("error", "NO"),
        ):
            pad = PadResult(status=status, trust_confirmed=None, risk_score=0.3)
            self.assertEqual(pad_public_decision_from_result(pad), expected, status)


class NightProbeQualityTests(SimpleTestCase):
    """A dark (night) selfie with a detectable face must not fail probe quality."""

    def test_dark_face_passes_quality(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import patch

        import numpy as np

        from monitoring_app import ml

        night = np.full((600, 337, 3), 12, dtype=np.uint8)
        face = SimpleNamespace(det_score=0.9, bbox=[60, 120, 280, 420], pose=None)
        with (
            patch.object(ml, "load_face_engine"),
            patch.object(
                ml, "_create_face_encoding_from_bgr", return_value=([0.1] * 512, face, [face])
            ),
        ):
            emb, meta = ml.create_face_encoding_with_probe_meta(night)
        self.assertIsNotNone(emb)
        self.assertTrue(meta["quality_pass"])
        brightness = meta["brightness_mean"]
        assert isinstance(brightness, float)
        self.assertLess(brightness, 22.0)


class TrustedSamplePrefetchTests(TestCase):
    """1:N search loads every staff's trusted samples in one query, not one per staff."""

    def test_collector_uses_prefetched_samples(self) -> None:
        from monitoring_app import ml
        from monitoring_app.models import Staff

        staff = [Staff.objects.create(pin=f"S90{i}S", name="N", surname="S") for i in range(3)]
        ml._prefetch_trusted_face_samples(staff)
        with self.assertNumQueries(0):
            for s in staff:
                self.assertEqual(ml._collect_trusted_staff_face_sample_records_for_staff(s), [])


class PoseFromKeypointsTests(SimpleTestCase):
    """Head pose from YuNet's 5 keypoints feeds the yaw/pitch probe gates."""

    def test_frontal_turned_and_tilted(self) -> None:
        import numpy as np

        from monitoring_app.ml import _pose_from_kps

        frontal = np.array([[40, 50], [80, 50], [60, 70], [45, 90], [75, 90]], np.float32)
        yaw, _pitch, roll = _pose_from_kps(frontal)
        self.assertLess(abs(yaw), 3)
        self.assertLess(abs(roll), 1)
        turned = frontal.copy()
        turned[2, 0] += 16
        self.assertGreater(_pose_from_kps(turned)[0], 25)
        tilted = frontal.copy()
        tilted[1, 1] += 40
        self.assertGreater(abs(_pose_from_kps(tilted)[2]), 30)


class FaceEngineDetectRetryTests(SimpleTestCase):
    """Close-up / dark avatars: retry on a padded, downscaled copy, boxes mapped back."""

    def test_retry_maps_padded_detection_to_original_coordinates(self) -> None:
        import numpy as np

        from monitoring_app.ml import _FaceEngine

        engine = object.__new__(_FaceEngine)
        img = np.zeros((1280, 960, 3), np.uint8)
        calls: list[tuple[int, ...]] = []

        def fake_detect(frame: np.ndarray) -> np.ndarray:
            calls.append(frame.shape)
            if len(calls) == 1:
                return np.empty((0, 15), np.float32)
            row = np.zeros((1, 15), np.float32)
            row[0, :4] = [260, 210, 100, 120]
            row[0, 4:6] = [300, 250]
            row[0, 14] = 0.9
            return row

        engine._detect = fake_detect  # type: ignore[method-assign]
        dets = engine.detect(img)
        self.assertEqual(calls[1], (960, 800, 3))
        np.testing.assert_allclose(dets[0, :6], [200, 100, 200, 240, 280, 180])
        self.assertAlmostEqual(float(dets[0, 14]), 0.9, places=5)


class VerifyDecisionLogTests(SimpleTestCase):
    """Every verify decision is one face_lab.log line (data on rejected frames)."""

    def test_one_log_line_per_decision(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import patch

        import numpy as np

        from monitoring_app import face_parsing, ml
        from monitoring_app.views import verify_staff_face

        live = {"checked": True, "status": "clean", "trust_confirmed": True}
        with (
            patch.object(ml, "load_image_from_memory", return_value=np.zeros((8, 8, 3), np.uint8)),
            patch("monitoring_app.photo_pad.check_photo_bgr", return_value=None),
            patch(
                "monitoring_app.face_verification_pad.liveness_payload_from_pad_result",
                return_value=live,
            ),
            patch.object(ml, "create_face_encoding_with_probe_meta", return_value=(None, {})),
            patch.object(ml, "build_runtime_gallery_embeddings", return_value=(None, {})),
            patch.object(face_parsing, "probe_bgr", return_value={}),
            self.assertLogs("monitoring_app.face_lab", "INFO") as logs,
        ):
            response = verify_staff_face(SimpleNamespace(pin="T0005T"), object())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["matched"])
        self.assertEqual(len(logs.records), 1)
        self.assertIn('"pin": "T0005T"', logs.output[0])
