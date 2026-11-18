import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from bot.request_schedule import parse_hours, in_window, describe_hours


class RequestScheduleTests(unittest.TestCase):
    def test_parse_hours(self):
        self.assertEqual(parse_hours("09:00-18:00"), (540, 1080))
        self.assertEqual(parse_hours("kapalı"), (None, None))
        self.assertEqual(describe_hours(540, 1080), "09:00-18:00")

    def test_invalid_hours(self):
        for text in ("24:00-18:00", "12:00-12:00", "hello", "9:00-12:00"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_hours(text)

    def test_day_window_inclusive_start_exclusive_end(self):
        tz = ZoneInfo("Europe/Istanbul")
        self.assertFalse(in_window(540, 1080, datetime(2026, 11, 18, 8, 59, tzinfo=tz)))
        self.assertTrue(in_window(540, 1080, datetime(2026, 11, 18, 9, 0, tzinfo=tz)))
        self.assertTrue(in_window(540, 1080, datetime(2026, 11, 18, 17, 59, tzinfo=tz)))
        self.assertFalse(in_window(540, 1080, datetime(2026, 11, 18, 18, 0, tzinfo=tz)))

    def test_overnight_window(self):
        tz = ZoneInfo("Europe/Istanbul")
        self.assertTrue(in_window(1320, 120, datetime(2026, 11, 18, 23, 0, tzinfo=tz)))
        self.assertTrue(in_window(1320, 120, datetime(2026, 11, 19, 1, 0, tzinfo=tz)))
        self.assertFalse(in_window(1320, 120, datetime(2026, 11, 19, 12, 0, tzinfo=tz)))

    def test_no_window(self):
        self.assertTrue(in_window(None, None, datetime(2026, 11, 18, 3, 0)))


if __name__ == "__main__":
    unittest.main()
