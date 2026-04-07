from __future__ import annotations

from django.test import SimpleTestCase, override_settings
from monitoring_app.face_verification_contract import (
    R_COLD_START_QUALITY_INSUFFICIENT,
    R_LIVENESS_FAILED,
    R_PAD_PIPELINE_FAILED,
    R_PROBE_QUALITY_LOW,
    R_SCORE_BELOW_COLD_START_THRESHOLD,
    R_SCORE_BELOW_VERIFIED_THRESHOLD,
    R_SCORE_BELOW_WEAK_GALLERY_THRESHOLD,
    R_WEAK_ENROLLMENT,
    LivenessPayload,
    QualityPayload,
)
from monitoring_app.face_verification_policy import decide_face_verify_binary

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

_GALLERY_STRONG_BD: dict[str, int] = {
    "mask_prototypes": 1,
    "avatar_prototypes": 1,
    "gallery_real_npy_prototypes": 0,
}

_EMPTY_GALLERY_BD: dict[str, int] = {}


def _call(
    *,
    quality: QualityPayload,
    live: LivenessPayload,
    score: float,
    gallery_templates: int,
    breakdown: dict[str, int],
    thr_v: float = 0.76,
    thr_w: float = 0.86,
    thr_cold: float = 0.835,
):
    return decide_face_verify_binary(
        **{
            "quality": quality,
            "liveness": live,
            "score": score,
            "gallery_templates": gallery_templates,
            "breakdown": breakdown,
            "threshold_verified": thr_v,
            "threshold_weak_gallery": thr_w,
            "threshold_cold_start": thr_cold,
        },
    )


class FaceVerifyPolicyPadMappingTests(SimpleTestCase):
    """PAD → binary decision: spoof vs pipeline error must not be conflated."""

    def test_pad_spoof_trust_false_is_no_liveness_fail(self) -> None:
        live: LivenessPayload = {
            "checked": True,
            "trust_confirmed": False,
            "status": "suspicious",
            "risk_score": 0.9,
            "model_version": "pad_v3",
            "tags": ["fasnet_fake"],
            "elapsed_ms": 10.0,
            "deepface_score": 0.8,
            "device_score": 0.2,
            "frame_score": 0.1,
            "quality_penalty": 0.0,
            "note": "",
        }
        matched, fd, _summary, st, codes, _thr, _gstr = _call(
            quality=_QUALITY_OK,
            live=live,
            score=0.99,
            gallery_templates=3,
            breakdown=_GALLERY_STRONG_BD,
        )
        self.assertFalse(matched)
        self.assertEqual(fd, "NO")
        self.assertEqual(st, "LIVENESS_FAIL")
        self.assertEqual(codes, [R_LIVENESS_FAILED])

    def test_pad_error_status_is_pad_error(self) -> None:
        live: LivenessPayload = {
            "checked": True,
            "trust_confirmed": None,
            "status": "error",
            "risk_score": 0.0,
            "model_version": "pad_v3",
            "tags": ["no_face"],
            "elapsed_ms": 5.0,
            "deepface_score": 0.0,
            "device_score": 0.0,
            "frame_score": 0.0,
            "quality_penalty": 0.0,
            "note": "",
        }
        matched, fd, _summary, st, codes, _thr, _gstr = _call(
            quality=_QUALITY_OK,
            live=live,
            score=0.99,
            gallery_templates=3,
            breakdown=_GALLERY_STRONG_BD,
        )
        self.assertFalse(matched)
        self.assertEqual(fd, "NO")
        self.assertEqual(st, "PAD_ERROR")
        self.assertEqual(codes, [R_PAD_PIPELINE_FAILED])

    def test_weak_gallery_high_score_yes_with_strict_threshold(self) -> None:
        weak_bd: dict[str, int] = {
            "mask_prototypes": 0,
            "avatar_prototypes": 1,
            "gallery_real_npy_prototypes": 0,
        }
        live: LivenessPayload = {
            "checked": True,
            "trust_confirmed": True,
            "status": "clean",
            "risk_score": 0.05,
            "model_version": "pad_v3",
            "tags": [],
            "elapsed_ms": 1.0,
            "deepface_score": 0.0,
            "device_score": 0.0,
            "frame_score": 0.0,
            "quality_penalty": 0.0,
            "note": "",
        }
        matched, fd, summary, st, codes, thr_applied, gstr = _call(
            quality=_QUALITY_OK,
            live=live,
            score=0.8724,
            gallery_templates=1,
            breakdown=weak_bd,
            thr_w=0.86,
        )
        self.assertTrue(matched)
        self.assertEqual(fd, "YES")
        self.assertEqual(st, "VERIFIED")
        self.assertEqual(codes, [])
        self.assertAlmostEqual(thr_applied, 0.86)
        self.assertEqual(gstr, "weak")
        self.assertIn("строг", summary.lower())

    def test_weak_gallery_mid_score_no_not_review(self) -> None:
        weak_bd: dict[str, int] = {
            "mask_prototypes": 0,
            "avatar_prototypes": 1,
            "gallery_real_npy_prototypes": 0,
        }
        live: LivenessPayload = {
            "checked": True,
            "trust_confirmed": True,
            "status": "clean",
            "risk_score": 0.05,
            "model_version": "pad_v3",
            "tags": [],
            "elapsed_ms": 1.0,
            "deepface_score": 0.0,
            "device_score": 0.0,
            "frame_score": 0.0,
            "quality_penalty": 0.0,
            "note": "",
        }
        matched, fd, _summary, st, codes, thr_applied, gstr = _call(
            quality=_QUALITY_OK,
            live=live,
            score=0.7832,
            gallery_templates=1,
            breakdown=weak_bd,
            thr_w=0.86,
        )
        self.assertFalse(matched)
        self.assertEqual(fd, "NO")
        self.assertEqual(st, "REJECTED")
        self.assertIn(R_WEAK_ENROLLMENT, codes)
        self.assertIn(R_SCORE_BELOW_WEAK_GALLERY_THRESHOLD, codes)
        self.assertAlmostEqual(thr_applied, 0.86)
        self.assertEqual(gstr, "weak")

    def test_zero_templates_is_no(self) -> None:
        live: LivenessPayload = {
            "checked": True,
            "trust_confirmed": True,
            "status": "clean",
            "risk_score": 0.01,
            "model_version": "pad_v3",
            "tags": [],
            "elapsed_ms": 1.0,
            "deepface_score": 0.0,
            "device_score": 0.0,
            "frame_score": 0.0,
            "quality_penalty": 0.0,
            "note": "",
        }
        matched, fd, _summary, st, codes, _thr, gstr = _call(
            quality=_QUALITY_OK,
            live=live,
            score=0.99,
            gallery_templates=0,
            breakdown=_EMPTY_GALLERY_BD,
        )
        self.assertFalse(matched)
        self.assertEqual(fd, "NO")
        self.assertEqual(st, "REJECTED")
        self.assertIn(R_WEAK_ENROLLMENT, codes)
        self.assertEqual(gstr, "weak")

    @override_settings(
        FACE_VERIFY_MIN_ENROLLMENT_SOURCES=2,
        FACE_VERIFY_MIN_TEMPLATES_STRONG=2,
    )
    def test_strong_gallery_verified_yes(self) -> None:
        live: LivenessPayload = {
            "checked": True,
            "trust_confirmed": True,
            "status": "clean",
            "risk_score": 0.02,
            "model_version": "pad_v3",
            "tags": [],
            "elapsed_ms": 1.0,
            "deepface_score": 0.0,
            "device_score": 0.0,
            "frame_score": 0.0,
            "quality_penalty": 0.0,
            "note": "",
        }
        matched, fd, _summary, st, codes, thr_applied, gstr = _call(
            quality=_QUALITY_OK,
            live=live,
            score=0.9,
            gallery_templates=3,
            breakdown=_GALLERY_STRONG_BD,
            thr_v=0.76,
        )
        self.assertTrue(matched)
        self.assertEqual(fd, "YES")
        self.assertEqual(st, "VERIFIED")
        self.assertEqual(codes, [])
        self.assertAlmostEqual(thr_applied, 0.76)
        self.assertEqual(gstr, "strong")

    @override_settings(
        FACE_VERIFY_MIN_ENROLLMENT_SOURCES=2,
        FACE_VERIFY_MIN_TEMPLATES_STRONG=2,
    )
    def test_strong_gallery_below_verified_threshold_no(self) -> None:
        live: LivenessPayload = {
            "checked": True,
            "trust_confirmed": True,
            "status": "clean",
            "risk_score": 0.02,
            "model_version": "pad_v3",
            "tags": [],
            "elapsed_ms": 1.0,
            "deepface_score": 0.0,
            "device_score": 0.0,
            "frame_score": 0.0,
            "quality_penalty": 0.0,
            "note": "",
        }
        matched, fd, _summary, st, codes, thr_applied, gstr = _call(
            quality=_QUALITY_OK,
            live=live,
            score=0.7,
            gallery_templates=3,
            breakdown=_GALLERY_STRONG_BD,
            thr_v=0.76,
        )
        self.assertFalse(matched)
        self.assertEqual(fd, "NO")
        self.assertEqual(st, "REJECTED")
        self.assertEqual(codes, [R_SCORE_BELOW_VERIFIED_THRESHOLD])
        self.assertAlmostEqual(thr_applied, 0.76)
        self.assertEqual(gstr, "strong")

    def test_cold_start_yes_when_no_gallery_real_and_strong_guards(self) -> None:
        live: LivenessPayload = {
            "checked": True,
            "trust_confirmed": True,
            "status": "clean",
            "risk_score": 0.02,
            "model_version": "pad_v3",
            "tags": [],
            "elapsed_ms": 1.0,
            "deepface_score": 0.0,
            "device_score": 0.0,
            "frame_score": 0.0,
            "quality_penalty": 0.0,
            "note": "",
        }
        q_cold_ok: QualityPayload = {
            "passed": True,
            "det_score": 0.5,
            "face_area_ratio": 0.02,
            "reason_codes": [],
        }
        bd_no_real = {
            "mask_prototypes": 0,
            "avatar_prototypes": 1,
            "gallery_real_npy_prototypes": 0,
        }
        matched, fd, _summary, st, codes, thr_applied, gstr = _call(
            quality=q_cold_ok,
            live=live,
            score=0.84,
            gallery_templates=1,
            breakdown=bd_no_real,
            thr_w=0.86,
            thr_cold=0.835,
        )
        self.assertTrue(matched)
        self.assertEqual(fd, "YES")
        self.assertEqual(st, "VERIFIED")
        self.assertEqual(codes, [])
        self.assertAlmostEqual(thr_applied, 0.835)
        self.assertEqual(gstr, "weak")

    def test_cold_start_no_below_cold_threshold(self) -> None:
        live: LivenessPayload = {
            "checked": True,
            "trust_confirmed": True,
            "status": "clean",
            "risk_score": 0.02,
            "model_version": "pad_v3",
            "tags": [],
            "elapsed_ms": 1.0,
            "deepface_score": 0.0,
            "device_score": 0.0,
            "frame_score": 0.0,
            "quality_penalty": 0.0,
            "note": "",
        }
        q_cold_ok: QualityPayload = {
            "passed": True,
            "det_score": 0.5,
            "face_area_ratio": 0.02,
            "reason_codes": [],
        }
        bd_no_real = {
            "mask_prototypes": 0,
            "avatar_prototypes": 1,
            "gallery_real_npy_prototypes": 0,
        }
        matched, fd, _summary, st, codes, thr_applied, _gstr = _call(
            quality=q_cold_ok,
            live=live,
            score=0.82,
            gallery_templates=1,
            breakdown=bd_no_real,
            thr_cold=0.835,
        )
        self.assertFalse(matched)
        self.assertEqual(fd, "NO")
        self.assertEqual(st, "REJECTED")
        self.assertIn(R_SCORE_BELOW_COLD_START_THRESHOLD, codes)
        self.assertAlmostEqual(thr_applied, 0.835)

    def test_cold_start_quality_guard_fails(self) -> None:
        live: LivenessPayload = {
            "checked": True,
            "trust_confirmed": True,
            "status": "clean",
            "risk_score": 0.02,
            "model_version": "pad_v3",
            "tags": [],
            "elapsed_ms": 1.0,
            "deepface_score": 0.0,
            "device_score": 0.0,
            "frame_score": 0.0,
            "quality_penalty": 0.0,
            "note": "",
        }
        q_weak_probe: QualityPayload = {
            "passed": True,
            "det_score": 0.36,
            "face_area_ratio": 0.02,
            "reason_codes": [],
        }
        bd_no_real = {
            "mask_prototypes": 0,
            "avatar_prototypes": 1,
            "gallery_real_npy_prototypes": 0,
        }
        matched, fd, _summary, st, codes, _thr, _gstr = _call(
            quality=q_weak_probe,
            live=live,
            score=0.99,
            gallery_templates=1,
            breakdown=bd_no_real,
        )
        self.assertFalse(matched)
        self.assertEqual(fd, "NO")
        self.assertEqual(st, "REJECTED")
        self.assertEqual(codes, [R_COLD_START_QUALITY_INSUFFICIENT])

    @override_settings(FACE_VERIFY_MIN_TEMPLATES_STRONG=3)
    def test_weak_with_gallery_real_uses_strict_not_cold(self) -> None:
        live: LivenessPayload = {
            "checked": True,
            "trust_confirmed": True,
            "status": "clean",
            "risk_score": 0.02,
            "model_version": "pad_v3",
            "tags": [],
            "elapsed_ms": 1.0,
            "deepface_score": 0.0,
            "device_score": 0.0,
            "frame_score": 0.0,
            "quality_penalty": 0.0,
            "note": "",
        }
        bd_with_real = {
            "mask_prototypes": 0,
            "avatar_prototypes": 1,
            "gallery_real_npy_prototypes": 1,
        }
        matched, fd, _summary, st, codes, thr_applied, _gstr = _call(
            quality=_QUALITY_OK,
            live=live,
            score=0.84,
            gallery_templates=2,
            breakdown=bd_with_real,
            thr_w=0.86,
            thr_cold=0.835,
        )
        self.assertFalse(matched)
        self.assertEqual(fd, "NO")
        self.assertEqual(st, "REJECTED")
        self.assertIn(R_SCORE_BELOW_WEAK_GALLERY_THRESHOLD, codes)
        self.assertAlmostEqual(thr_applied, 0.86)

    def test_quality_fail_before_score_when_pad_clean(self) -> None:
        live: LivenessPayload = {
            "checked": True,
            "trust_confirmed": True,
            "status": "clean",
            "risk_score": 0.01,
            "model_version": "pad_v3",
            "tags": [],
            "elapsed_ms": 1.0,
            "deepface_score": 0.0,
            "device_score": 0.0,
            "frame_score": 0.0,
            "quality_penalty": 0.0,
            "note": "",
        }
        matched, fd, _summary, st, codes, _thr, _gstr = _call(
            quality=_QUALITY_FAIL,
            live=live,
            score=0.99,
            gallery_templates=3,
            breakdown=_GALLERY_STRONG_BD,
        )
        self.assertFalse(matched)
        self.assertEqual(fd, "NO")
        self.assertEqual(st, "QUALITY_FAIL")
        self.assertEqual(codes[0], R_PROBE_QUALITY_LOW)
