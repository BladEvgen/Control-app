from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from monitoring_app.face_bootstrap_quality import bootstrap_quality_decision


class FaceBootstrapQualityTests(SimpleTestCase):
    def test_accepts_strict_probe_pass(self) -> None:
        ok, detail = bootstrap_quality_decision(
            {"face_present": True, "quality_pass": True},
            "front",
        )

        self.assertTrue(ok)
        self.assertEqual(detail["reason"], "strict_quality_passed")

    def test_accepts_usable_webcam_sample_even_if_verify_probe_is_strict(self) -> None:
        ok, detail = bootstrap_quality_decision(
            {
                "face_present": True,
                "quality_pass": False,
                "quality_reason_codes": ["blurry_face"],
                "det_score": 0.62,
                "face_area_ratio": 0.08,
                "blur_laplacian_var": 18.0,
                "brightness_mean": 130.0,
                "pose_yaw": 12.0,
                "pose_pitch": 4.0,
            },
            "front",
        )

        self.assertTrue(ok)
        self.assertEqual(detail["reason"], "bootstrap_relaxed_quality_passed")

    def test_rejects_tiny_uncertain_face(self) -> None:
        ok, detail = bootstrap_quality_decision(
            {
                "face_present": True,
                "quality_pass": False,
                "det_score": 0.12,
                "face_area_ratio": 0.001,
                "blur_laplacian_var": 40.0,
                "brightness_mean": 120.0,
            },
            "front",
        )

        self.assertFalse(ok)
        self.assertIn("low_det_score", detail["reason_codes"])
        self.assertIn("small_face", detail["reason_codes"])

    @override_settings(FACE_BOOTSTRAP_SAMPLE_SIDE_MAX_ABS_YAW=62.0)
    def test_side_sample_allows_controlled_head_turn(self) -> None:
        ok, detail = bootstrap_quality_decision(
            {
                "face_present": True,
                "quality_pass": False,
                "quality_reason_codes": ["face_yaw_too_large"],
                "det_score": 0.7,
                "face_area_ratio": 0.1,
                "blur_laplacian_var": 24.0,
                "brightness_mean": 126.0,
                "pose_yaw": 51.0,
                "pose_pitch": 6.0,
            },
            "left",
        )

        self.assertTrue(ok)
        self.assertEqual(detail["reason"], "bootstrap_relaxed_quality_passed")

    @override_settings(FACE_BOOTSTRAP_SAMPLE_FRONT_MAX_ABS_YAW=42.0)
    def test_front_sample_rejects_excessive_turn(self) -> None:
        ok, detail = bootstrap_quality_decision(
            {
                "face_present": True,
                "quality_pass": False,
                "det_score": 0.8,
                "face_area_ratio": 0.1,
                "blur_laplacian_var": 24.0,
                "brightness_mean": 126.0,
                "pose_yaw": 56.0,
                "pose_pitch": 6.0,
            },
            "front",
        )

        self.assertFalse(ok)
        self.assertIn("face_yaw_too_large", detail["reason_codes"])
