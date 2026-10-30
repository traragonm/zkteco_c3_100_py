import unittest
from datetime import datetime

from zkc3 import rtlog
from zkc3.controller import parse_key_values
from zkc3.device_time import decode_device_time, encode_device_time


class RtLogTests(unittest.TestCase):
    def test_scan_and_status_lines(self):
        raw = ("2026-10-29 09:14:31,0,QR-8F21A0C4,1,27,0,4\r\n"
               "2026-10-29 09:14:32,7,12345678,1,0,1,4\r\n"
               "2026-10-29 09:14:33,2,0,0,255,0,0\r\n"
               "rác\r\n")
        events, statuses = rtlog.parse(raw)

        self.assertEqual(len(events), 2)
        a, b = events
        self.assertEqual((a.code, a.door, a.event_type, a.direction, a.granted), ("QR-8F21A0C4", 1, 27, "Vào", False))
        self.assertEqual(a.event_name, "Thẻ chưa đăng ký")
        self.assertEqual(a.time, datetime(2026, 10, 29, 9, 14, 31))
        self.assertEqual((b.pin, b.direction, b.granted), ("7", "Ra", True))

        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0].door1_sensor, 2)

    def test_door_events_are_not_scans(self):
        events, _ = rtlog.parse("2026-10-29 09:00:00,0,0,1,200,2,200")
        self.assertFalse(rtlog.is_scan_event(events[0]))
        self.assertEqual(events[0].event_name, "Cửa đã mở")

    def test_unknown_event_name(self):
        self.assertEqual(rtlog.event_name(999), "Sự kiện 999")


class DeviceTimeTests(unittest.TestCase):
    def test_round_trip(self):
        t = datetime(2026, 10, 30, 23, 59, 58)
        self.assertEqual(decode_device_time(encode_device_time(t)), t)

    def test_known_value(self):
        self.assertEqual(encode_device_time(datetime(2000, 1, 1, 0, 0, 1)), 1)
        self.assertEqual(encode_device_time(datetime(2000, 2, 1)), 31 * 86400)

    def test_invalid_day_returns_none(self):
        # 31/2 tồn tại trong lịch 12×31 của C3 nhưng không phải ngày hợp lệ.
        self.assertIsNone(decode_device_time(((0 * 12 + 1) * 31 + 30) * 86400))


class KeyValueTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_key_values("~SerialNumber=AB12, FirmVer=AC Ver 4.7 ,bad,=x"),
                         {"~serialnumber": "AB12", "firmver": "AC Ver 4.7"})


if __name__ == "__main__":
    unittest.main()
