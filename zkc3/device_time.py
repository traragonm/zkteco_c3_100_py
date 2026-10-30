"""C3 lưu giờ dạng số giây theo lịch 12 tháng × 31 ngày tính từ năm 2000."""

from __future__ import annotations

from datetime import datetime


def encode_device_time(t: datetime) -> int:
    return (((t.year - 2000) * 12 * 31 + (t.month - 1) * 31 + (t.day - 1)) * 86400
            + (t.hour * 60 + t.minute) * 60 + t.second)


def decode_device_time(v: int) -> datetime | None:
    v, sec = divmod(v, 60)
    v, minute = divmod(v, 60)
    v, hour = divmod(v, 24)
    v, day = divmod(v, 31)
    year, month = divmod(v, 12)
    try:
        return datetime(year + 2000, month + 1, day + 1, hour, minute, sec)
    except ValueError:
        return None
