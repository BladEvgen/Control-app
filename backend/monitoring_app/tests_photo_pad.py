import datetime
import json

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

    def test_background_display_context_without_fake_goes_review_not_default_clean(
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
        self.assertEqual(result.status, STATUS_REVIEW)
        self.assertIn("pad_rule:background_screen_context_review", result.tags)

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
            )
        )
        self.assertEqual(result.status, STATUS_REVIEW)
        self.assertIsNone(result.trust_confirmed)
        self.assertIn("pad_rule:fake_reflection_guard_review", result.tags)

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
        self.assertIn("pad_trace_v8", struct_tags[0])
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

    def test_image_quality_degraded_without_spoof_goes_to_review(self):
        """Severe quality degradation routes to review, not suspicious (quality ≠ spoof)."""
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
        self.assertEqual(result.status, STATUS_REVIEW)
        self.assertIn("pad_rule:presentation_insufficient_input_review", result.tags)

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
                    "recapture_fft_periodicity",
                    "recapture_gradient_aniso",
                ],
                recapture_score=0.35,
            )
        )
        self.assertEqual(result.status, STATUS_REVIEW)
        self.assertIn("pad_rule:spoof_uncertain_texture_ambiguous_review", result.tags)


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
        self.assertIn("spoof_risk", payload["presentation"])
        self.assertIn("is_degraded", payload["quality"])
        self.assertNotIn("почему", json.dumps(payload))
        self.assertNotIn("why", payload)

    def test_clean_payload_exposes_branch_without_duplicate_reason_lists(self):
        struct = {
            "schema": "pad_trace_v8",
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

    def test_suspicious_strong_corroboration_presentation_confidence_high(self):
        """Corroborated ``suspicious`` must not use the old low default confidence floor."""
        struct = {
            "schema": "pad_trace_v8",
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
        self.staff = Staff.objects.create(
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
        lesson = LessonAttendance.objects.create(
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
