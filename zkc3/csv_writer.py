from __future__ import annotations

import csv
import threading
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .models import AccessEvent

HEADER = ["Time", "Door", "Direction", "Code", "Pin", "EventType", "EventName", "VerifyType", "Verify", "Result"]


class EventCsvWriter:
    """Lưu mỗi sự kiện quét QR vào file CSV theo ngày."""

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    @property
    def current_file(self) -> Path:
        return self.directory / f"events_{datetime.now():%Y-%m-%d}.csv"

    def append(self, e: AccessEvent) -> None:
        with self._lock:
            path = self.current_file
            is_new = not path.exists()
            # BOM chỉ ghi ở đầu file mới để Excel đọc đúng tiếng Việt.
            with open(path, "a", encoding="utf-8-sig" if is_new else "utf-8", newline="") as f:
                w = csv.writer(f)
                if is_new:
                    w.writerow(HEADER)
                w.writerow(_row(e))

    @staticmethod
    def export(path: str | Path, events: Iterable[AccessEvent]) -> None:
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(HEADER)
            w.writerows(_row(e) for e in events)


def _row(e: AccessEvent) -> list:
    return [f"{e.time:%Y-%m-%d %H:%M:%S}", e.door, e.direction, e.code, e.pin,
            e.event_type, e.event_name, e.verify_type, e.verify_note, e.result]
