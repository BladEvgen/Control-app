import datetime
import json
from typing import TYPE_CHECKING, Any, cast

import numpy as np
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from monitoring_app.models import LessonAttendance, Staff
from monitoring_app.pad_diagnostics import (
    PAD_DIAGNOSTICS_VERSION,
    build_pad_diagnostic_payload,
)
from monitoring_app.photo_pad import (
    STATUS_CLEAN,
    STATUS_REVIEW,
    STATUS_SUSPICIOUS,
    check_photo,
    spoof_probability,
    verdict_from_probability,
)

if TYPE_CHECKING:
    from django.contrib.auth.models import User
else:
    User = get_user_model()


class PadVerdictMappingTests(SimpleTestCase):
    """Spoof probability -> status / trust / operator copy, using head thresholds."""

    HEAD = {
        "t_clean": 0.2,
        "t_suspicious": 0.8,
        "intercept": 0.0,
        "_coef": np.ones(2, np.float32),
        "_mean": np.zeros(2, np.float32),
        "_scale": np.ones(2, np.float32),
    }

    def test_three_bands(self):
        cases = [
            (0.05, STATUS_CLEAN, True),
            (0.5, STATUS_REVIEW, None),
            (0.95, STATUS_SUSPICIOUS, False),
        ]
        for p, status, trust in cases:
            r = verdict_from_probability(p, self.HEAD)
            self.assertEqual((r.status, r.trust_confirmed, r.risk_score), (status, trust, p))
            struct = next(t for t in r.tags if t.startswith("pad_struct:"))
            self.assertEqual(json.loads(struct[len("pad_struct:") :])["status"], status)

    def test_operator_reason_only_when_not_clean(self):
        has_reason = [
            any(t.startswith("pad_ui_reason:") for t in verdict_from_probability(p, self.HEAD).tags)
            for p in (0.05, 0.5, 0.95)
        ]
        self.assertEqual(has_reason, [False, True, True])

    def test_spoof_probability_is_logistic(self):
        self.assertAlmostEqual(spoof_probability(np.zeros(2, np.float32), self.HEAD), 0.5)
        self.assertGreater(spoof_probability(np.ones(2, np.float32), self.HEAD), 0.85)

    def test_unreadable_image_is_error(self):
        self.assertEqual(check_photo("/nonexistent/x.jpg").status, "error")


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


class LessonAttendancePhotoResetTests(TestCase):
    def setUp(self):
        self.staff = cast(Any, Staff).objects.create(
            pin="S998877S",
            name="Pad",
            surname="Tester",
            department=None,
        )
        self.user = User.objects.create_user(
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

        self.assertEqual(lesson.photo_spoof_status, LessonAttendance.PHOTO_SPOOF_STATUS_PENDING)
        self.assertIsNone(lesson.photo_spoof_score)
        self.assertEqual(lesson.photo_spoof_tags, [])
        self.assertIsNone(lesson.photo_spoof_checked_at)
        self.assertEqual(lesson.photo_spoof_model_version, "")
        self.assertIsNone(lesson.photo_trust_confirmed)
        self.assertEqual(lesson.photo_manual_verdict, LessonAttendance.PHOTO_MANUAL_VERDICT_NONE)
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
        lesson.pk = 1
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


class PadRescoreCachedTests(TestCase):
    """Weekly retrain re-scores cached photos in bulk, never operator-judged rows."""

    def test_rescore_skips_manual_and_sets_verdicts(self):
        from unittest.mock import patch

        from monitoring_app.management.commands import train_photo_pad

        staff = cast(Any, Staff).objects.create(pin="S700700S", name="Pad", surname="Bulk")
        common = dict(
            staff=staff,
            subject_name="PAD",
            tutor_id=1,
            tutor="Tutor",
            first_in=timezone.now(),
            latitude=43.24,
            longitude=76.95,
            date_at=datetime.date.today(),
        )
        auto = cast(Any, LessonAttendance).objects.create(staff_image_path="/tmp/a.jpg", **common)
        manual = cast(Any, LessonAttendance).objects.create(
            staff_image_path="/tmp/b.jpg",
            photo_manual_verdict=LessonAttendance.PHOTO_MANUAL_VERDICT_CLEAN,
            **common,
        )
        cache = {auto.id: np.ones(2, np.float32) * 5, manual.id: np.ones(2, np.float32) * 5}
        with patch.object(train_photo_pad, "load_head", return_value=PadVerdictMappingTests.HEAD):
            self.assertEqual(train_photo_pad.rescore_cached(cache), 1)
        auto.refresh_from_db()
        manual.refresh_from_db()
        self.assertEqual(auto.photo_spoof_status, STATUS_SUSPICIOUS)
        self.assertEqual(manual.photo_spoof_status, LessonAttendance.PHOTO_SPOOF_STATUS_PENDING)
