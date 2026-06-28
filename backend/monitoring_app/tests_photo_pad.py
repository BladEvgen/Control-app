import datetime
import json
from typing import Any, cast

import numpy as np
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from monitoring_app.models import LessonAttendance, Staff
from monitoring_app.pad_diagnostics import (
    PAD_DIAGNOSTICS_VERSION,
    build_pad_diagnostic_payload,
)
from monitoring_app.pad_synthetic_audit import SYNTHETIC_REVIEW_RATE_AUDIT_SCENARIOS
from monitoring_app.photo_pad import (
    STATUS_CLEAN,
    STATUS_ERROR,
    STATUS_REVIEW,
    STATUS_SUSPICIOUS,
    DecisionInputs,
    _decide,
    _minifasnet_onnx_input,
    _runtime_cache,
    _score_minifasnet_onnx,
)


class PadDecisionTests(SimpleTestCase):
    def test_low_quality_without_device_goes_to_review(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.92,
                device_score=0.0,
                frame_score=0.05,
                quality_penalty=0.7,
                tags=["fasnet_fake", "quality_poor"],
            )
        )
        self.assertEqual(result.status, STATUS_REVIEW)

    def test_device_plus_frame_and_fake_goes_to_suspicious(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.88,
                device_score=0.62,
                frame_score=0.52,
                quality_penalty=0.1,
                tags=["fasnet_fake", "device_present:cell phone", "screen_frame"],
            )
        )
        self.assertEqual(result.status, STATUS_SUSPICIOUS)

    def test_very_high_deepfake_without_screen_signal_goes_suspicious(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.98,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.1,
                tags=["fasnet_fake"],
            )
        )
        self.assertEqual(result.status, STATUS_SUSPICIOUS)
        self.assertIn(
            "pad_rule:fake_high_confidence_no_geometry_suspicious", result.tags
        )

    def test_mid_deepfake_with_mid_screen_signal_goes_to_suspicious(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.84,
                device_score=0.24,
                frame_score=0.26,
                quality_penalty=0.1,
                tags=["fasnet_fake", "device_present:laptop"],
            )
        )
        self.assertEqual(result.status, STATUS_SUSPICIOUS)

    def test_minifasnet_fake_tag_counts_as_spoof_model_signal(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.84,
                device_score=0.24,
                frame_score=0.26,
                quality_penalty=0.1,
                tags=["minifasnet_onnx_fake"],
            )
        )
        self.assertEqual(result.status, STATUS_SUSPICIOUS)
        self.assertIn("pad_rule:fake_mid_plus_dual_mid_geometry", result.tags)

    def test_model_disagreement_when_fasnet_live_goes_to_review(self):
        """FasNet live + elevated ONNX with zero corroboration must go to review,
        not auto-clean: neither model's raw score reliably separates real from
        spoofed faces in this disagreement zone (confirmed by manual image audit),
        so a human must decide instead of trusting FasNet's "live" call blindly."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.04,
                tags=[
                    "fasnet_real",
                    "minifasnet_onnx_fake",
                    "spoof_model_disagreement",
                    "minifasnet_onnx_advisory_when_fasnet_real",
                ],
                model_scores={"fasnet": 0.0, "minifasnet_onnx": 0.92},
            )
        )
        self.assertEqual(result.status, STATUS_REVIEW)
        self.assertIsNone(result.trust_confirmed)
        self.assertIn("pad_rule:fake_default_review_not_clean", result.tags)

    def test_model_disagreement_without_fasnet_live_stays_review(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.46,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.04,
                tags=[
                    "minifasnet_onnx_fake",
                    "spoof_model_disagreement",
                ],
                model_scores={"minifasnet_onnx": 0.92},
            )
        )
        self.assertEqual(result.status, STATUS_REVIEW)
        self.assertIsNone(result.trust_confirmed)
        self.assertIn("pad_rule:spoof_model_disagreement_review", result.tags)

    def test_weak_multi_device_clutter_does_not_escalate_live_selfie(self):
        """Regression: COCO tags phone+laptop+tv at ~0.41 must not force review."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.41,
                frame_score=0.0,
                quality_penalty=0.0,
                tags=[
                    "fasnet_real",
                    "device_on_face:cell phone",
                    "device_on_face:laptop",
                    "device_on_face:tv",
                    "face_reflection_screen_like",
                    "face_color_histogram_screen_like",
                ],
                face_area_ratio=0.11,
                face_reflection_score=0.36,
            )
        )
        self.assertEqual(result.status, STATUS_CLEAN)
        self.assertIn("pad_rule:live_selfie_surface_noise_uncertain_clean", result.tags)

    def test_bezel_only_reflection_does_not_hard_reject_live_face(self):
        """Regression: screen_bezel in background without on-face device."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.0,
                tags=[
                    "fasnet_real",
                    "screen_bezel_context",
                    "face_reflection_screen_like",
                ],
                frame_global_score=0.37,
                face_area_ratio=0.12,
                face_reflection_score=0.89,
            )
        )
        self.assertEqual(result.status, STATUS_CLEAN)

    def test_confirmed_tv_on_face_keeps_color_suspicious_for_spoof(self):
        """Regression: real replay should stay suspicious when TV on face is strong."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.56,
                frame_score=0.0,
                quality_penalty=0.0,
                tags=[
                    "fasnet_real",
                    "device_on_face:tv",
                    "face_reflection_screen_like",
                    "face_color_histogram_screen_like",
                ],
                face_area_ratio=0.09,
                face_reflection_score=0.78,
            )
        )
        self.assertEqual(result.status, STATUS_SUSPICIOUS)
        self.assertTrue(
            any(
                tag in result.tags
                for tag in (
                    "pad_rule:color_histogram_display_suspicious",
                    "pad_rule:face_reflection_display_suspicious",
                )
            )
        )
        ui = [t for t in result.tags if t.startswith("pad_ui_reason:")]
        self.assertEqual(len(ui), 1)
        self.assertIn("пересъёмка", ui[0].lower())

    def test_fake_background_display_review_ui_reason_mentions_background(self):
        from monitoring_app.photo_pad import _pad_ui_reason_text

        text = _pad_ui_reason_text("fake_background_display_review", STATUS_REVIEW)
        self.assertIn("фоне", text)

    def test_live_selfie_clean_has_no_pad_ui_reason(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.27,
                frame_score=0.0,
                quality_penalty=0.0,
                tags=[
                    "fasnet_real",
                    "device_on_face:tv",
                    "face_reflection_screen_like",
                ],
                face_area_ratio=0.12,
                face_reflection_score=0.80,
            )
        )
        self.assertEqual(result.status, STATUS_CLEAN)
        self.assertFalse(any(t.startswith("pad_ui_reason:") for t in result.tags))

    def test_weak_tv_on_face_live_selfie_not_suspicious(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.27,
                frame_score=0.0,
                quality_penalty=0.0,
                tags=[
                    "fasnet_real",
                    "device_on_face:tv",
                    "face_reflection_screen_like",
                    "face_color_histogram_screen_like",
                ],
                face_area_ratio=0.12,
                face_reflection_score=0.80,
            )
        )
        self.assertEqual(result.status, STATUS_CLEAN)
        self.assertIn("pad_rule:live_selfie_surface_noise_uncertain_clean", result.tags)

    def test_live_selfie_color_reflection_without_geometry_goes_to_review(self):
        """2026-06-02 false-positive pattern (fasnet live + color + glare, no screen)
        is indistinguishable, on existing signals, from confirmed close-up screen
        recaptures with the same fingerprint (zero geometry, high reflection/color,
        model disagreement) found via manual photo audit in 2026-06-22. Real selfies
        and real spoofs produce identical scores here, so this now goes to human
        review instead of auto-clean, accepting more manual checks to avoid letting
        spoofs through silently."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.0,
                tags=[
                    "fasnet_real",
                    "minifasnet_onnx_fake",
                    "spoof_model_disagreement",
                    "face_reflection_screen_like",
                ],
                face_area_ratio=0.11,
                face_reflection_score=0.78,
            )
        )
        self.assertEqual(result.status, STATUS_REVIEW)
        self.assertIsNone(result.trust_confirmed)

    def test_ensemble_consensus_escalates_independent_families(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.04,
                tags=[],
                recapture_score=0.6,
                device_bg_score=0.7,
                frame_global_score=0.7,
                face_area_ratio=0.08,
            )
        )
        self.assertEqual(result.status, STATUS_SUSPICIOUS)
        self.assertIn("pad_rule:ensemble_consensus_suspicious", result.tags)

    def test_mid_fake_with_background_display_context_goes_suspicious(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.84,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.08,
                tags=["fasnet_fake", "screen_bezel_context"],
                frame_global_score=0.36,
            )
        )
        self.assertEqual(result.status, STATUS_SUSPICIOUS)
        self.assertIn(
            "pad_rule:fake_mid_plus_background_display_suspicious", result.tags
        )

    def test_background_display_context_without_fake_weak_context_uses_uncertain_clean(
        self,
    ):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.0,
                tags=["screen_bezel_context"],
                frame_global_score=0.31,
            )
        )
        self.assertEqual(result.status, STATUS_CLEAN)
        self.assertIsNone(result.trust_confirmed)
        self.assertIn("pad_rule:background_screen_context_uncertain_clean", result.tags)

    def test_background_display_context_strong_context_uses_uncertain_clean(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.0,
                tags=["screen_bezel_context"],
                frame_global_score=0.45,
            )
        )
        self.assertEqual(result.status, STATUS_CLEAN)
        self.assertIsNone(result.trust_confirmed)
        self.assertIn("pad_rule:background_screen_context_uncertain_clean", result.tags)

    def test_background_device_only_context_without_fake_uses_uncertain_clean(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.0,
                tags=["device_background:tv"],
                device_bg_score=0.69,
                frame_global_score=0.0,
            )
        )
        self.assertEqual(result.status, STATUS_CLEAN)
        self.assertIsNone(result.trust_confirmed)
        self.assertIn("pad_rule:background_screen_context_uncertain_clean", result.tags)

    def test_fake_with_only_one_mid_geometry_stays_review(self):
        """One geometry shoulder is no longer enough for hard suspicious."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.52,
                device_score=0.22,
                frame_score=0.03,
                quality_penalty=0.1,
                tags=["fasnet_fake", "device_present:cell phone"],
            )
        )
        self.assertEqual(result.status, STATUS_REVIEW)
        self.assertIsNone(result.trust_confirmed)
        self.assertIn("pad_rule:fake_default_review_not_clean", result.tags)

    def test_shield_blocks_weak_geometry_review_for_normal_live(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.13,
                frame_score=0.11,
                quality_penalty=0.05,
                tags=[],
            )
        )
        self.assertEqual(result.status, STATUS_CLEAN)
        self.assertIn("pad_rule:default_clean", result.tags)

    def test_shield_not_applied_when_quality_penalty_above_cap(self):
        """Quality penalty above shield cap drops the shield but keeps a calm clean result."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.13,
                frame_score=0.11,
                quality_penalty=0.42,
                tags=[],
            )
        )
        self.assertEqual(result.status, STATUS_CLEAN)
        self.assertIn("pad_rule:default_clean", result.tags)

    def test_strong_screen_dual_mid_geometry_auto_suspicious(self):
        """Strong screen context still needs face-gated frame corroboration for suspicious."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.56,
                frame_score=0.36,
                quality_penalty=0.05,
                tags=[],
                recapture_score=0.0,
                face_area_ratio=0.05,
            )
        )
        self.assertEqual(result.status, STATUS_SUSPICIOUS)
        self.assertFalse(result.trust_confirmed)
        self.assertIn(
            "pad_rule:strong_screen_dual_mid_geometry_suspicious", result.tags
        )

    def test_no_fake_dual_geometry_small_face_is_review_not_suspicious(self):
        """Background-like strong geometry on a tiny face must not auto-suspicious."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.60,
                frame_score=0.50,
                quality_penalty=0.05,
                tags=[],
                face_area_ratio=0.02,
            )
        )
        self.assertEqual(result.status, STATUS_REVIEW)
        self.assertIn("pad_rule:presentation_insufficient_input_review", result.tags)

    def test_strong_device_only_signal_stays_uncertain_clean(self):
        """Device-only context no longer escalates to spoof without corroboration."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.59,
                frame_score=0.0,
                quality_penalty=0.1,
                tags=["device_present:tv"],
            )
        )
        self.assertEqual(result.status, STATUS_CLEAN)
        self.assertIsNone(result.trust_confirmed)
        self.assertIn("pad_rule:device_only_context_uncertain_clean", result.tags)

    def test_quality_poor_with_screen_signal_stays_in_review(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.22,
                frame_score=0.26,
                quality_penalty=0.6,
                tags=["quality_poor"],
            )
        )
        self.assertEqual(result.status, STATUS_REVIEW)

    def test_clean_signal_goes_to_clean(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.0,
                tags=[],
            )
        )
        self.assertEqual(result.status, STATUS_CLEAN)

    def test_high_fasnet_fake_without_geometry_stays_review_without_corroboration(
        self,
    ):
        """High FasNet alone stays review until face-gated corroboration appears."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.78,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.05,
                tags=["fasnet_fake"],
                recapture_score=0.0,
            )
        )
        self.assertEqual(result.status, STATUS_REVIEW)
        self.assertIn("pad_rule:fake_default_review_not_clean", result.tags)

    def test_mid_fasnet_fake_without_geometry_still_review_narrow_band(self):
        """Between review_min and autonomous floor → review remains the narrow fallback."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.70,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.05,
                tags=["fasnet_fake"],
                recapture_score=0.0,
            )
        )
        self.assertEqual(result.status, STATUS_REVIEW)
        self.assertIn("pad_rule:fake_default_review_not_clean", result.tags)

    def test_weak_fasnet_fake_without_geometry_goes_clean(self):
        """Below decision_deepfake_review_min with no mid geometry → auto clean (baseline PAD)."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.40,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.05,
                tags=["fasnet_fake"],
                recapture_score=0.0,
            )
        )
        self.assertEqual(result.status, STATUS_CLEAN)
        self.assertTrue(result.trust_confirmed)
        self.assertIn("pad_rule:fake_low_confidence_no_geometry_clean", result.tags)

    def test_mid_confidence_fake_without_geometry_goes_review_not_clean(self):
        """Regression: neural in [spoof_model_family_mid, decision_deepfake_review_min)
        with zero geometry must not silently auto-clean. Historical replay of confirmed
        real spoofs (pad_v7 manual_verdict=suspicious) showed deepfake_score in 0.50-0.64
        auto-resolving to clean because this band fell through fake_low_confidence_no_geometry_clean
        before ever reaching the spoof_model_family_mid review check below it.
        """
        for score in (0.50, 0.55, 0.60, 0.64):
            with self.subTest(score=score):
                result = _decide(
                    DecisionInputs(
                        decode_error=False,
                        has_face=True,
                        deepface_score=score,
                        device_score=0.0,
                        frame_score=0.0,
                        quality_penalty=0.05,
                        tags=["fasnet_fake"],
                        recapture_score=0.0,
                    )
                )
                self.assertEqual(result.status, STATUS_REVIEW)
                self.assertIn("pad_rule:fake_default_review_not_clean", result.tags)

    def test_reflection_guard_fake_without_geometry_stays_review(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.63,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.0,
                tags=["fasnet_fake", "glasses_reflection_guard"],
                recapture_score=0.0,
                face_area_ratio=0.06,
                face_reflection_score=0.9,
            )
        )
        self.assertEqual(result.status, STATUS_REVIEW)
        self.assertIsNone(result.trust_confirmed)
        self.assertIn("pad_rule:fake_reflection_guard_review", result.tags)

    def test_face_reflection_with_screen_context_goes_suspicious(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.24,
                frame_score=0.26,
                quality_penalty=0.05,
                tags=["face_reflection_screen_like"],
                face_area_ratio=0.06,
                face_reflection_score=0.62,
            )
        )
        self.assertEqual(result.status, STATUS_SUSPICIOUS)
        self.assertFalse(result.trust_confirmed)
        self.assertIn("pad_rule:face_reflection_display_suspicious", result.tags)

    def test_fasnet_live_blur_tv_disagreement_goes_to_review(self):
        """Blur + weak TV box + MiniFAS noise while FasNet live (June 2 Baygozha class).

        Model disagreement is no longer trusted as automatically benign: with a
        device confirmed on-face and poor image quality, this now requires human
        review rather than silently resolving to clean."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.549,
                frame_score=0.0,
                quality_penalty=0.35,
                tags=[
                    "fasnet_real",
                    "minifasnet_onnx_fake",
                    "spoof_model_disagreement",
                    "minifasnet_onnx_advisory_when_fasnet_real",
                    "device_on_face:tv",
                    "quality_blur",
                    "quality_poor",
                    "glasses_reflection_guard",
                    "face_color_histogram_screen_like",
                ],
                face_area_ratio=0.158,
                face_reflection_score=0.0,
            )
        )
        self.assertEqual(result.status, STATUS_REVIEW)
        self.assertIsNone(result.trust_confirmed)
        self.assertIn("pad_rule:quality_poor_with_face_gated_screen", result.tags)

    def test_fasnet_live_tv_reflection_disagreement_goes_to_suspicious(self):
        """FasNet live + reflection heuristics without neural spoof (June 2 Dudikova class).

        With a device confirmed on-face plus a strong reflection screen
        signature, model disagreement must escalate to suspicious rather than
        being waved through as clean."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.563,
                frame_score=0.0,
                quality_penalty=0.0,
                tags=[
                    "fasnet_real",
                    "minifasnet_onnx_fake",
                    "spoof_model_disagreement",
                    "device_on_face:tv",
                    "face_reflection_screen_like",
                ],
                face_area_ratio=0.089,
                face_reflection_score=0.78,
            )
        )
        self.assertEqual(result.status, STATUS_SUSPICIOUS)
        self.assertFalse(result.trust_confirmed)

    def test_face_reflection_without_context_does_not_auto_reject(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.05,
                tags=["face_reflection_screen_like"],
                face_area_ratio=0.06,
                face_reflection_score=0.9,
            )
        )
        self.assertNotEqual(result.status, STATUS_SUSPICIOUS)
        self.assertIn("pad_rule:face_reflection_isolated_uncertain_clean", result.tags)

    def test_isolated_reflection_with_model_disagreement_goes_to_review(self):
        """Model disagreement is treated as genuine uncertainty, not automatically
        benign, even with only an isolated reflection signal and no color
        corroboration: catching real screen-recapture attacks takes priority
        over avoiding the extra manual review."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.4998,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.35,
                tags=[
                    "fasnet_real",
                    "minifasnet_onnx_fake",
                    "spoof_model_disagreement",
                    "face_reflection_screen_like",
                ],
                face_area_ratio=0.20,
                face_reflection_score=0.8227,
            )
        )
        self.assertEqual(result.status, STATUS_REVIEW)
        self.assertIsNone(result.trust_confirmed)

    def test_fake_plus_face_reflection_goes_suspicious(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.84,
                device_score=0.40,
                frame_score=0.0,
                quality_penalty=0.05,
                tags=["fasnet_fake", "face_reflection_screen_like"],
                face_area_ratio=0.06,
                face_reflection_score=0.62,
            )
        )
        self.assertEqual(result.status, STATUS_SUSPICIOUS)
        self.assertFalse(result.trust_confirmed)
        self.assertIn("pad_rule:fake_plus_face_reflection_suspicious", result.tags)

    def test_fake_plus_face_reflection_without_geometry_stays_review(self):
        """Regression: real selfies (normal face crop, no screen/frame/recapture
        evidence) were wrongly auto-rejected because face_reflection alone
        corroborated a miscalibrated neural 'fake' call.
        """
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.70,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.35,
                tags=[
                    "fasnet_fake",
                    "minifasnet_onnx_fake",
                    "face_reflection_screen_like",
                ],
                face_area_ratio=0.204,
                face_reflection_score=0.8325,
                model_scores={"minifasnet_onnx": 0.60},
            )
        )
        self.assertEqual(result.status, STATUS_REVIEW)

    def test_global_verdict_trace_includes_jury_and_debate(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.56,
                frame_score=0.0,
                quality_penalty=0.0,
                tags=[
                    "fasnet_real",
                    "device_on_face:tv",
                    "face_reflection_screen_like",
                ],
                face_area_ratio=0.09,
                face_reflection_score=0.78,
            )
        )
        struct_tag = next(t for t in result.tags if t.startswith("pad_struct:"))
        self.assertIn("global_verdict", struct_tag)
        self.assertIn("neural_debate", struct_tag)
        global_tag = next(t for t in result.tags if t.startswith("pad_global:"))
        self.assertIn("debate", global_tag)

    def test_pad_struct_tag_present(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.0,
                tags=[],
            )
        )
        struct_tags = [t for t in result.tags if t.startswith("pad_struct:")]
        self.assertEqual(len(struct_tags), 1)
        self.assertIn("pad_trace_v12", struct_tags[0])
        self.assertIn('"product_outcome":"clean"', struct_tags[0])

    def test_fake_plus_strong_recapture_without_geometry_stays_review(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.84,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.05,
                tags=["fasnet_fake", "recapture_fft_periodicity"],
                recapture_score=0.40,
            )
        )
        self.assertEqual(result.status, STATUS_REVIEW)
        self.assertIn("pad_rule:fake_default_review_not_clean", result.tags)

    def test_decode_error_goes_to_error(self):
        result = _decide(
            DecisionInputs(
                decode_error=True,
                has_face=False,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.0,
                tags=["decode_error"],
            )
        )
        self.assertEqual(result.status, STATUS_ERROR)

    def test_presentation_risk_ignores_quality_penalty(self):
        """Fused spoof risk must not drop when image quality worsens (separate axes)."""
        r_clean_qp = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.5,
                device_score=0.2,
                frame_score=0.15,
                quality_penalty=0.05,
                tags=["fasnet_fake"],
                recapture_score=0.05,
            )
        )
        r_poor_qp = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.5,
                device_score=0.2,
                frame_score=0.15,
                quality_penalty=0.85,
                tags=["fasnet_fake", "quality_poor"],
                recapture_score=0.05,
            )
        )
        self.assertAlmostEqual(r_clean_qp.risk_score, r_poor_qp.risk_score, places=4)

    def test_image_quality_degraded_without_spoof_uses_uncertain_clean(self):
        """Severe quality degradation alone should not create manual queue work."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.72,
                tags=["quality_poor"],
                recapture_score=0.0,
            )
        )
        self.assertEqual(result.status, STATUS_CLEAN)
        self.assertIsNone(result.trust_confirmed)
        self.assertIn("pad_rule:image_quality_uncertain_clean", result.tags)

    def test_mild_quality_poor_alone_uncertain_clean_not_review_queue(self):
        """Borderline poor quality without presentation hints → clean, trust None (review-rate cap)."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.46,
                tags=["quality_poor"],
                recapture_score=0.0,
            )
        )
        self.assertEqual(result.status, STATUS_CLEAN)
        self.assertIsNone(result.trust_confirmed)
        self.assertIn("pad_rule:image_quality_uncertain_clean", result.tags)

    def test_insufficient_input_without_spoof_signals_uses_uncertain_clean(self):
        """Quality-limited ROI alone should not create operator work when spoof signals are absent."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.48,
                tags=["quality_blur", "quality_face_edge_crop", "quality_poor"],
                recapture_score=0.0,
                face_area_ratio=0.17,
            )
        )
        self.assertEqual(result.status, STATUS_CLEAN)
        self.assertIsNone(result.trust_confirmed)
        self.assertIn(
            "pad_rule:presentation_insufficient_input_uncertain_clean",
            result.tags,
        )
        self.assertNotIn("pad_rule:presentation_insufficient_input_review", result.tags)

    def test_severe_quality_poor_without_spoof_signals_uses_uncertain_clean(self):
        """Even strong quality degradation should avoid review when no presentation hints exist."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.55,
                tags=["quality_blur", "quality_low_contrast", "quality_poor"],
                recapture_score=0.0,
                face_area_ratio=0.15,
            )
        )
        self.assertEqual(result.status, STATUS_CLEAN)
        self.assertIsNone(result.trust_confirmed)
        self.assertIn("pad_rule:image_quality_uncertain_clean", result.tags)
        self.assertNotIn("pad_rule:presentation_insufficient_input_review", result.tags)

    def test_blur_only_without_spoof_signals_uses_uncertain_clean(self):
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.35,
                tags=["quality_blur"],
                recapture_score=0.0,
                face_area_ratio=0.16,
            )
        )
        self.assertEqual(result.status, STATUS_CLEAN)
        self.assertIsNone(result.trust_confirmed)
        self.assertIn("pad_rule:image_quality_uncertain_clean", result.tags)
        self.assertNotIn("pad_rule:presentation_insufficient_input_review", result.tags)

    def test_moderate_strong_recapture_isolated_clean_without_context(self):
        """Isolated strong recapture without dual texture cues → clean, not review."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.05,
                tags=[],
                recapture_score=0.55,
            )
        )
        self.assertEqual(result.status, STATUS_CLEAN)
        self.assertIsNone(result.trust_confirmed)
        self.assertIn(
            "pad_rule:recapture_isolated_single_cue_texture_clean", result.tags
        )

    def test_isolated_recapture_extreme_single_channel_uncertain_clean(self):
        """Very high isolated single-channel recapture → uncertain clean (not review)."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.05,
                tags=[],
                recapture_score=0.94,
            )
        )
        self.assertEqual(result.status, STATUS_CLEAN)
        self.assertIsNone(result.trust_confirmed)
        self.assertIn(
            "pad_rule:recapture_isolated_extreme_single_channel_uncertain_clean",
            result.tags,
        )

    def test_isolated_recapture_high_without_dual_cue_uncertain_clean(self):
        """Strong isolated recapture below single-channel extreme → uncertain clean."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.05,
                tags=[],
                recapture_score=0.86,
            )
        )
        self.assertEqual(result.status, STATUS_CLEAN)
        self.assertIsNone(result.trust_confirmed)
        self.assertIn(
            "pad_rule:recapture_isolated_single_cue_texture_clean", result.tags
        )

    def test_isolated_recapture_high_single_cue_goes_clean(self):
        """High combined recapture without dual inner cues does not alone force review."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.05,
                tags=["recapture_fft_periodicity"],
                recapture_score=0.68,
            )
        )
        self.assertEqual(result.status, STATUS_CLEAN)
        self.assertIsNone(result.trust_confirmed)
        self.assertIn(
            "pad_rule:recapture_isolated_single_cue_texture_clean", result.tags
        )

    def test_isolated_recapture_dual_cues_texture_ambiguous_review_without_other_channels(
        self,
    ):
        """Dual inner-face texture + strong rec without FasNet/geometry → review."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.05,
                tags=[
                    "recapture_fft_periodicity",
                    "recapture_gradient_aniso",
                ],
                recapture_score=0.58,
            )
        )
        self.assertEqual(result.status, STATUS_REVIEW)
        self.assertIsNone(result.trust_confirmed)
        self.assertIn(
            "pad_rule:recapture_isolated_dual_texture_ambiguous_review",
            result.tags,
        )

    def test_isolated_dual_texture_with_quality_penalty_texture_ambiguous_review(self):
        """Dual texture + strong rec + penalty: review when calm FasNet/geometry."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.22,
                tags=[
                    "recapture_fft_periodicity",
                    "recapture_gradient_aniso",
                ],
                recapture_score=0.696,
            )
        )
        self.assertEqual(result.status, STATUS_REVIEW)
        self.assertIn(
            "pad_rule:recapture_isolated_dual_texture_ambiguous_review",
            result.tags,
        )

    def test_isolated_extreme_dual_sharp_frame_moiré_uncertain_clean(self):
        """Live-like: dual cues, very high rec, sharp frame → moiré forgiveness clean."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.02,
                tags=[
                    "recapture_fft_periodicity",
                    "recapture_gradient_aniso",
                ],
                recapture_score=1.0,
            )
        )
        self.assertEqual(result.status, STATUS_CLEAN)
        self.assertIsNone(result.trust_confirmed)
        self.assertIn(
            "pad_rule:recapture_isolated_extreme_moire_live_uncertain_clean",
            result.tags,
        )

    def test_strong_recapture_corroborated_dual_geometry_suspicious_without_fake(self):
        """Strong recapture + suspicious-tier dual geometry can escalate past review."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.40,
                frame_score=0.50,
                quality_penalty=0.05,
                tags=[],
                recapture_score=0.55,
                face_area_ratio=0.05,
            )
        )
        self.assertEqual(result.status, STATUS_SUSPICIOUS)
        self.assertTrue(
            any(
                tag in result.tags
                for tag in (
                    "pad_rule:no_fake_recapture_strong_corroborated_dual_geometry",
                    "pad_rule:no_fake_dual_suspicious_geometry",
                )
            ),
        )

    def test_fake_high_quality_without_geometry_goes_suspicious(self):
        """Very high fake confidence must not fall back to weak review when geometry is calm."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.97,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.02,
                tags=["fasnet_fake"],
                recapture_score=0.0,
            )
        )
        self.assertEqual(result.status, STATUS_SUSPICIOUS)
        self.assertIn(
            "pad_rule:fake_high_confidence_no_geometry_suspicious", result.tags
        )

    def test_high_fake_with_blur_stays_spoof_review_not_insufficient_input(self):
        """Blur must not hide an otherwise obvious spoof-like fake score."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.999,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.35,
                tags=["fasnet_fake", "quality_blur"],
                recapture_score=0.0,
                face_area_ratio=0.23,
            )
        )
        self.assertEqual(result.status, STATUS_SUSPICIOUS)
        self.assertNotIn("pad_rule:presentation_insufficient_input_review", result.tags)
        self.assertIn(
            "pad_rule:fake_high_confidence_no_geometry_suspicious", result.tags
        )

    def test_mid_fake_with_blur_uses_spoof_review_not_insufficient_input(self):
        """Moderate fake evidence with blur should stay in spoof review, not input-failure review."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.46,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.35,
                tags=["fasnet_fake", "quality_blur"],
                recapture_score=0.0,
                face_area_ratio=0.29,
            )
        )
        self.assertEqual(result.status, STATUS_REVIEW)
        self.assertIsNone(result.trust_confirmed)
        self.assertIn("pad_rule:fake_quality_limited_review", result.tags)
        self.assertNotIn("pad_rule:presentation_insufficient_input_review", result.tags)

    def test_isolated_dual_texture_blur_goes_review_not_suspicious(self):
        """Blurry ROI must not become texture-only suspicious (manual review instead)."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.35,
                tags=[
                    "quality_blur",
                    "recapture_fft_periodicity",
                    "recapture_gradient_aniso",
                ],
                recapture_score=0.58,
            )
        )
        self.assertEqual(result.status, STATUS_REVIEW)
        self.assertIn("pad_rule:presentation_insufficient_input_review", result.tags)

    def test_isolated_dual_texture_tiny_face_goes_review(self):
        """Very small face area blocks texture-primary suspicious."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.05,
                tags=[
                    "recapture_fft_periodicity",
                    "recapture_gradient_aniso",
                ],
                recapture_score=0.58,
                face_area_ratio=0.02,
            )
        )
        self.assertEqual(result.status, STATUS_REVIEW)
        self.assertIn("pad_rule:presentation_insufficient_input_review", result.tags)

    def test_strong_rec_loose_context_blur_goes_review(self):
        """Loose-context strong rec (present frame below suspicious tier) + blur → review."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.05,
                frame_score=0.28,
                quality_penalty=0.35,
                tags=["quality_blur"],
                recapture_score=0.55,
            )
        )
        self.assertEqual(result.status, STATUS_REVIEW)
        self.assertIn("pad_rule:presentation_insufficient_input_review", result.tags)

    def test_elevated_quality_penalty_blocks_texture_dual_suspicious(self):
        """High quality penalty without ``quality_poor`` still blocks texture suspicious."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.32,
                tags=[
                    "recapture_fft_periodicity",
                    "recapture_gradient_aniso",
                ],
                recapture_score=0.58,
            )
        )
        self.assertEqual(result.status, STATUS_REVIEW)
        self.assertIn("pad_rule:presentation_insufficient_input_review", result.tags)

    def test_strong_rec_loose_context_roi_ok_is_ambiguous_review_not_suspicious(self):
        """Strong isolated single-cue recapture now stays uncertain clean."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.05,
                frame_score=0.28,
                quality_penalty=0.05,
                tags=[],
                recapture_score=0.55,
            )
        )
        self.assertEqual(result.status, STATUS_CLEAN)
        self.assertIn(
            "pad_rule:recapture_isolated_single_cue_texture_clean",
            result.tags,
        )

    def test_spoof_uncertain_mid_rec_texture_ambiguous_review(self):
        """FasNet unavailable + mid rec + texture corroboration → review, not suspicious."""
        result = _decide(
            DecisionInputs(
                decode_error=False,
                has_face=True,
                deepface_score=0.0,
                device_score=0.0,
                frame_score=0.0,
                quality_penalty=0.05,
                tags=[
                    "fasnet_unavailable",
                    "pad_spoof_model_missing",
                    "recapture_fft_periodicity",
                    "recapture_gradient_aniso",
                ],
                recapture_score=0.35,
            )
        )
        self.assertEqual(result.status, STATUS_REVIEW)
        self.assertIn("pad_rule:spoof_uncertain_texture_ambiguous_review", result.tags)


class PadGuideModelFeatureTests(SimpleTestCase):
    def tearDown(self):
        for key in (
            "minifasnet_onnx_session",
            "minifasnet_onnx_error",
        ):
            _runtime_cache.pop(key, None)

    def test_minifasnet_onnx_input_uses_bgr_80x80_nchw(self):
        """This checkpoint expects raw 0..255 pixel values, not /255-scaled
        floats — confirmed empirically: /255 scaling made the model output
        a constant ~0.9997 "fake" score on every manually-verified-clean
        photo, regardless of content."""
        img = np.zeros((120, 100, 3), dtype=np.uint8)
        img[:, :, 0] = 255

        tensor = _minifasnet_onnx_input(img, (25, 25, 40, 50))

        self.assertIsNotNone(tensor)
        tensor_value = cast(np.ndarray, tensor)
        self.assertEqual(tensor_value.shape, (1, 3, 80, 80))
        self.assertEqual(tensor_value.dtype, np.float32)
        self.assertAlmostEqual(float(tensor_value[0, 0].max()), 255.0)

    def test_minifasnet_onnx_score_sums_print_and_replay_classes(self):
        """Index 1 is "real" in the minivision-ai class layout; index 1's
        probability must NOT be counted as spoof evidence. Logits here keep
        index 1 (real) low and split mass across index 0 (print) and index 2
        (replay) so the test fails if either spoof class is dropped."""

        class FakeOnnxSession:
            def run(self, output_names, feed):
                self.output_names = output_names
                self.input_shape = feed["input"].shape
                return [np.array([[3.0, -2.0, 3.5]], dtype=np.float32)]

        fake = FakeOnnxSession()
        _runtime_cache["minifasnet_onnx_session"] = (fake, "input", "output")
        _runtime_cache["minifasnet_onnx_error"] = ""
        img = np.zeros((120, 100, 3), dtype=np.uint8)

        score, tags = _score_minifasnet_onnx(img, (25, 25, 40, 50))

        self.assertIsNotNone(score)
        score_value = cast(float, score)
        self.assertGreater(score_value, 0.98)
        self.assertEqual(fake.output_names, ["output"])
        self.assertEqual(fake.input_shape, (1, 3, 80, 80))
        self.assertIn("minifasnet_onnx_used", tags)
        self.assertIn("minifasnet_onnx_fake", tags)

    def test_minifasnet_onnx_score_excludes_real_class_probability(self):
        """A confident "real" prediction (index 1 dominant) must score low,
        not high — regression test for the inverted-index bug where
        probs[1] (real) was being added into the spoof score."""

        class RealFaceOnnxSession:
            def run(self, output_names, feed):
                # index 1 ("real") dominates: this is a live, non-spoof face.
                return [np.array([[-3.7, 4.4, -0.7]], dtype=np.float32)]

        _runtime_cache["minifasnet_onnx_session"] = (
            RealFaceOnnxSession(),
            "input",
            "output",
        )
        _runtime_cache["minifasnet_onnx_error"] = ""
        img = np.zeros((120, 100, 3), dtype=np.uint8)

        score, tags = _score_minifasnet_onnx(img, (25, 25, 40, 50))

        self.assertIsNotNone(score)
        score_value = cast(float, score)
        self.assertLess(score_value, 0.1)
        self.assertNotIn("minifasnet_onnx_fake", tags)


class PadDiagnosticsContractTests(SimpleTestCase):
    """English-keyed public diagnostics (no localized field names in JSON)."""

    def test_build_payload_uses_english_top_level_keys(self):
        payload = build_pad_diagnostic_payload(
            status="review",
            trust_confirmed=None,
            risk_score=0.41,
            model_version="pad_v6",
            elapsed_ms=12.3,
            deepface_score=0.0,
            device_score=0.1,
            frame_score=0.12,
            quality_penalty=0.5,
            device_bg_score=0.2,
            frame_global_score=0.15,
            recapture_score=0.05,
            tags=["quality_poor", "pad_rule:image_quality_degraded_review"],
        )
        self.assertEqual(payload["diagnostics_version"], PAD_DIAGNOSTICS_VERSION)
        self.assertIn("decision", payload)
        self.assertIn("presentation", payload)
        self.assertIn("quality", payload)
        self.assertIn("background_context", payload)
        self.assertIn("uncertainty", payload)
        self.assertIn("trace", payload)
        self.assertEqual(payload["decision"]["final_decision"], "review")
        self.assertEqual(payload["decision"]["operator_action"], "retry_photo")
        self.assertIn("spoof_risk", payload["presentation"])
        self.assertIn("is_degraded", payload["quality"])
        self.assertNotIn("почему", json.dumps(payload))
        self.assertNotIn("why", payload)

    def test_clean_payload_exposes_branch_without_duplicate_reason_lists(self):
        struct = {
            "schema": "pad_trace_v10",
            "branch": "default_clean",
            "product_outcome": "clean",
        }
        struct_tag = f"pad_struct:{json.dumps(struct, separators=(',', ':'))}"
        payload = build_pad_diagnostic_payload(
            status="clean",
            trust_confirmed=True,
            risk_score=0.02,
            model_version="pad_v6",
            elapsed_ms=1.0,
            deepface_score=0.0,
            device_score=0.0,
            frame_score=0.0,
            quality_penalty=0.0,
            device_bg_score=0.0,
            frame_global_score=0.0,
            recapture_score=0.0,
            tags=[struct_tag],
        )
        codes = payload["uncertainty"]["clean_reason_codes"]
        self.assertEqual(codes, [])
        self.assertEqual(payload["uncertainty"]["review_reason_codes"], [])
        self.assertEqual(
            payload["decision"]["decision_branch"],
            "default_clean",
        )
        self.assertEqual(payload["decision"]["product_outcome"], "clean")
        self.assertEqual(payload["decision"]["operator_action"], "accept")

    def test_review_action_distinguishes_retry_from_manual_review(self):
        retry_payload = build_pad_diagnostic_payload(
            status="review",
            trust_confirmed=None,
            risk_score=0.18,
            model_version="pad_v6",
            elapsed_ms=1.0,
            deepface_score=0.0,
            device_score=0.0,
            frame_score=0.0,
            quality_penalty=0.55,
            device_bg_score=0.0,
            frame_global_score=0.0,
            recapture_score=0.0,
            tags=["pad_rule:presentation_insufficient_input_review", "quality_poor"],
        )
        manual_payload = build_pad_diagnostic_payload(
            status="review",
            trust_confirmed=None,
            risk_score=0.46,
            model_version="pad_v6",
            elapsed_ms=1.0,
            deepface_score=0.46,
            device_score=0.0,
            frame_score=0.0,
            quality_penalty=0.04,
            device_bg_score=0.0,
            frame_global_score=0.0,
            recapture_score=0.0,
            tags=["pad_rule:spoof_model_disagreement_review"],
        )
        self.assertEqual(retry_payload["decision"]["operator_action"], "retry_photo")
        self.assertEqual(
            manual_payload["decision"]["operator_action"],
            "manual_review",
        )

    def test_suspicious_strong_corroboration_presentation_confidence_high(self):
        """Corroborated ``suspicious`` must not use the old low default confidence floor."""
        struct = {
            "schema": "pad_trace_v10",
            "branch": "no_fake_dual_suspicious_geometry",
            "product_outcome": "suspicious",
        }
        struct_tag = f"pad_struct:{json.dumps(struct, separators=(',', ':'))}"
        payload = build_pad_diagnostic_payload(
            status="suspicious",
            trust_confirmed=False,
            risk_score=0.88,
            model_version="pad_v6",
            elapsed_ms=5.0,
            deepface_score=0.0,
            device_score=0.62,
            frame_score=0.52,
            quality_penalty=0.05,
            device_bg_score=0.0,
            frame_global_score=0.0,
            recapture_score=0.1,
            tags=[struct_tag],
        )
        self.assertGreaterEqual(
            float(payload["decision"]["presentation_confidence"]),
            0.7,
        )

    def test_no_russian_keys_in_payload(self):
        payload = build_pad_diagnostic_payload(
            status="clean",
            trust_confirmed=True,
            risk_score=0.05,
            model_version="pad_v6",
            elapsed_ms=1.0,
            deepface_score=0.0,
            device_score=0.0,
            frame_score=0.0,
            quality_penalty=0.0,
            device_bg_score=0.0,
            frame_global_score=0.0,
            recapture_score=0.0,
            tags=[],
        )
        blob = json.dumps(payload, ensure_ascii=False)
        self.assertNotRegex(blob, r"[А-Яа-яЁё]")


class PadReviewRateAuditTests(SimpleTestCase):
    """Explicit review-rate regression guard on a fixed synthetic scenario set."""

    def test_synthetic_mix_keeps_review_fraction_below_half(self):
        counts: dict[str, int] = {}
        for _label, inp in SYNTHETIC_REVIEW_RATE_AUDIT_SCENARIOS:
            r = _decide(inp)
            counts[r.status] = counts.get(r.status, 0) + 1
        total = sum(counts.values())
        review_n = counts.get(STATUS_REVIEW, 0)
        review_frac = review_n / total
        self.assertLess(
            review_frac,
            0.5,
            msg=f"review_rate={review_frac:.2f} counts={counts} (tighten PAD if spurious)",
        )


class LessonAttendancePhotoResetTests(TestCase):
    def setUp(self):
        self.staff = cast(Any, Staff).objects.create(
            pin="S998877S",
            name="Pad",
            surname="Tester",
            department=None,
        )
        self.user = get_user_model().objects.create_user(
            username="pad_admin",
            password="test-pass-123",
        )

    def test_photo_change_resets_manual_override(self):
        lesson = cast(Any, LessonAttendance).objects.create(
            staff=self.staff,
            subject_name="PAD",
            tutor_id=1,
            tutor="Tutor",
            first_in=timezone.now(),
            latitude=43.24,
            longitude=76.95,
            date_at=datetime.date.today(),
            staff_image_path="/tmp/pad_old.jpg",
            photo_spoof_status=LessonAttendance.PHOTO_SPOOF_STATUS_SUSPICIOUS,
            photo_spoof_score=0.91,
            photo_spoof_tags=["fasnet_fake", "device_present:cell phone"],
            photo_spoof_checked_at=timezone.now(),
            photo_spoof_model_version="pad_v2",
            photo_trust_confirmed=False,
            photo_manual_verdict=LessonAttendance.PHOTO_MANUAL_VERDICT_SUSPICIOUS,
            photo_manual_comment="manual suspicious",
            photo_manual_by=self.user,
            photo_manual_at=timezone.now(),
        )

        lesson.staff_image_path = "/tmp/pad_new.jpg"
        lesson.save(update_fields=["staff_image_path"])
        lesson.refresh_from_db()

        self.assertEqual(
            lesson.photo_spoof_status, LessonAttendance.PHOTO_SPOOF_STATUS_PENDING
        )
        self.assertIsNone(lesson.photo_spoof_score)
        self.assertEqual(lesson.photo_spoof_tags, [])
        self.assertIsNone(lesson.photo_spoof_checked_at)
        self.assertEqual(lesson.photo_spoof_model_version, "")
        self.assertIsNone(lesson.photo_trust_confirmed)
        self.assertEqual(
            lesson.photo_manual_verdict, LessonAttendance.PHOTO_MANUAL_VERDICT_NONE
        )
        self.assertEqual(lesson.photo_manual_comment, "")
        self.assertIsNone(lesson.photo_manual_by)
        self.assertIsNone(lesson.photo_manual_at)


class PadAdminSummaryTests(TestCase):
    """Admin operator panel must follow ``photo_spoof_status`` and ``pad_ui_reason``."""

    def test_suspicious_with_neural_fake_shows_spoof_not_insufficient(self):
        from monitoring_app.models import LessonAttendance
        from monitoring_app.pad_admin_summary import (
            _effective_verdict_line,
            _is_auto_insufficient_input,
            format_lesson_attendance_antifraud_operator_panel,
        )

        tags = [
            "fasnet_fake",
            "minifasnet_onnx_fake",
            "pad_rule:fake_plus_face_reflection_suspicious",
            "pad_ui_reason:Обе модели видят подмену; отражение и цвета лица как на экране.",
            'pad_struct:{"schema":"pad_trace_v12","branch":"fake_plus_face_reflection_suspicious","product_outcome":"suspicious","deepfake_score":0.84}',
            "pad_evidence:df=0.840,dev_f=0.000,dev_bg=0.000,frm_f=0.000,frm_gl=0.598,rec=0.000,refl=0.821,clr=0.700,qp=0.475",
            "quality_poor",
        ]
        lesson = LessonAttendance(
            photo_spoof_status=LessonAttendance.PHOTO_SPOOF_STATUS_SUSPICIOUS,
            photo_spoof_score=0.54,
            photo_spoof_tags=tags,
            photo_spoof_model_version="pad_v12",
            photo_trust_confirmed=False,
        )
        self.assertFalse(_is_auto_insufficient_input(lesson))
        label, _source, _note = _effective_verdict_line(lesson)
        self.assertEqual(label, "Подозрительно")
        html = str(format_lesson_attendance_antifraud_operator_panel(lesson))
        self.assertIn("Обе модели видят подмену", html)
        self.assertNotIn("Недостаточно данных", html)
        self.assertNotIn("не подозрение на подмену", html)
        self.assertNotIn("pad_global:", html)

    def test_insufficient_input_only_when_review_rule(self):
        from monitoring_app.models import LessonAttendance
        from monitoring_app.pad_admin_summary import _is_auto_insufficient_input

        review_tags = [
            "pad_rule:presentation_insufficient_input_review",
            "quality_poor",
        ]
        review = LessonAttendance(
            photo_spoof_status=LessonAttendance.PHOTO_SPOOF_STATUS_REVIEW,
            photo_spoof_tags=review_tags,
        )
        self.assertTrue(_is_auto_insufficient_input(review))
        suspicious = LessonAttendance(
            photo_spoof_status=LessonAttendance.PHOTO_SPOOF_STATUS_SUSPICIOUS,
            photo_spoof_tags=review_tags,
        )
        self.assertFalse(_is_auto_insufficient_input(suspicious))
