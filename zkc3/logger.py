from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

from .models import LogEntry, LogLevel


class AppLogger:
    """Ghi log kết nối ra file theo ngày và phát sự kiện cho UI. Gọi được từ nhiều thread."""

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._listeners: list[Callable[[LogEntry], None]] = []

    @property
    def current_file(self) -> Path:
        return self.directory / f"connection_{datetime.now():%Y-%m-%d}.log"

    def subscribe(self, listener: Callable[[LogEntry], None]) -> None:
        self._listeners.append(listener)

    def debug(self, msg: str) -> None: self.write(LogLevel.DEBUG, msg)
    def info(self, msg: str) -> None: self.write(LogLevel.INFO, msg)
    def warn(self, msg: str) -> None: self.write(LogLevel.WARN, msg)
    def error(self, msg: str) -> None: self.write(LogLevel.ERROR, msg)

    def write(self, level: LogLevel, msg: str) -> None:
        entry = LogEntry(datetime.now(), level, msg)
        with self._lock:
            try:
                with open(self.current_file, "a", encoding="utf-8") as f:
                    f.write(f"{entry}\n")
            except OSError:
                pass  # không để lỗi ghi file làm hỏng luồng kết nối
        for listener in self._listeners:
            listener(entry)
