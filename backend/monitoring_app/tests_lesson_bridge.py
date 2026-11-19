"""Credit for time between lesson marks: decaying trust, travel deducted between buildings."""

import datetime

from django.test import SimpleTestCase, override_settings

from monitoring_app import utils
from monitoring_app.services import attendance_day as ad

UTC = datetime.timezone.utc
NORTH = (43.2400, 76.9000)
SOUTH = (43.1770, 76.9000)  # ~7 km south


def mark(hh, mm, *, place=NORTH, spoof="clean", manual="none"):
    start = datetime.datetime(2026, 11, 19, hh, mm, tzinfo=UTC)
    return dict(
        first_in=start,
        last_out=start + datetime.timedelta(minutes=5),
        latitude=place[0],
        longitude=place[1],
        photo_spoof_status=spoof,
        photo_manual_verdict=manual,
    )


def credited_minutes(rows):
    return utils.merge_work_intervals_to_total_seconds(ad.lesson_presence_intervals(rows)) // 60


@override_settings(
    LESSON_BRIDGE_FULL_MINUTES=150,
    LESSON_BRIDGE_LIMIT_MINUTES=360,
    LESSON_BRIDGE_DECAY=0.5,
    LESSON_BRIDGE_RADIUS_M=300,
    LESSON_TRAVEL_BASE_MINUTES=15,
    LESSON_TRAVEL_MIN_PER_KM=4.0,
    LESSON_TRAVEL_MAX_MINUTES=60,
)
class LessonBridgeTests(SimpleTestCase):
    def test_arrival_and_leave_marks_count_whole_visit(self):
        rows = [mark(14, 4), mark(16, 37)]
        self.assertEqual(credited_minutes(rows), 158)  # 14:04 -> 16:42, gap under 2.5 h

    def test_single_mark_keeps_only_its_own_minutes(self):
        self.assertEqual(credited_minutes([mark(14, 4)]), 5)

    def test_unconfirmed_photo_does_not_bridge_until_cleared(self):
        rows = [mark(14, 4), mark(16, 37, spoof="review")]
        self.assertEqual(ad.lesson_bridges(rows)[0]["reason"], ad.BRIDGE_PHOTO)
        self.assertEqual(credited_minutes(rows), 10)
        rows[1]["photo_manual_verdict"] = "clean"
        self.assertEqual(credited_minutes(rows), 158)

    def test_move_to_other_building_loses_only_travel_time(self):
        rows = [mark(9, 0), mark(11, 0, place=SOUTH)]
        bridge = ad.lesson_bridges(rows)[0]
        self.assertAlmostEqual(bridge["travel_seconds"] / 60, 15 + 4 * 7, delta=1)
        self.assertAlmostEqual(credited_minutes(rows), 10 + 115 - 43, delta=1)

    def test_far_building_travel_is_capped_at_an_hour(self):
        far = (43.0600, 76.9000)  # ~20 km
        bridge = ad.lesson_bridges([mark(9, 0), mark(12, 0, place=far)])[0]
        self.assertEqual(bridge["travel_seconds"], 3600)

    def test_morning_and_evening_marks_are_capped(self):
        # 2.5 h full + (6 - 2.5) h at half = 4 h 15 min, not the whole 9 h
        self.assertEqual(credited_minutes([mark(9, 0), mark(18, 0)]), 10 + 255)

    def test_more_marks_bring_credit_closer_to_real_time(self):
        two = credited_minutes([mark(9, 0), mark(17, 0)])
        three = credited_minutes([mark(9, 0), mark(13, 0), mark(17, 0)])
        self.assertLess(two, three)
        self.assertLessEqual(three, 8 * 60 + 5)

    def test_merge_day_unions_bridge_with_turnstile_once(self):
        sa = [
            dict(
                first_in=None,
                last_out=None,
                effective_work_intervals=[
                    {"start": "2026-11-19T15:00:00+00:00", "end": "2026-11-19T18:00:00+00:00"}
                ],
            )
        ]
        merged = ad.merge_day(sa, [mark(14, 4), mark(16, 37)])
        self.assertEqual(merged["effective_work_seconds"] // 60, 236)  # 14:04 -> 18:00
