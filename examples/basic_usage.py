"""
Ví dụ dùng zkc3 như thư viện: kết nối, đọc thông tin, mở cửa, theo dõi lượt quét 30 giây.

    python examples/basic_usage.py 192.168.1.201
    python examples/basic_usage.py --simulate
"""

import sys
import threading

from zkc3 import AppLogger, C3Controller, ConnectionSettings
from zkc3.rtlog import is_scan_event


def main() -> None:
    simulate = "--simulate" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ip = args[0] if args else "192.168.1.201"

    log = AppLogger("logs")
    log.subscribe(lambda e: print(f"[{e.level.name}] {e.message}"))

    if simulate:
        from zkc3.simulator import FakePullSdk
        device = C3Controller(log, FakePullSdk)
    else:
        device = C3Controller(log)  # tìm plcommpro.dll trong ./sdk hoặc $ZKC3_SDK_DIR

    def on_events(events):
        for e in events:
            if not is_scan_event(e):
                continue
            print(f">>> Quét: {e.code} cửa {e.door} — {e.event_name}")
            if not e.granted:
                # Ví dụ quy tắc tự viết: mã bắt đầu bằng "QR-" thì mở cửa 5 giây.
                # (Gọi SDK từ thread polling là an toàn: controller tự tuần tự hoá.)
                if e.code.startswith("QR-"):
                    device.set_door(e.door or 1, 5)

    device.events_received.connect(on_events)

    with device:
        if not device.connect(ConnectionSettings(ip, password="")):
            sys.exit(1)
        info = device.refresh_device_info()
        print(f"Serial={info.serial}  Firmware={info.firmware}  Số cửa={info.lock_count}")

        users = device.get_table("user", "CardNo,Pin,Name")
        print(f"Có {len(users or [])} người dùng trên thiết bị")

        print("Theo dõi 30 giây...")
        threading.Event().wait(30)


if __name__ == "__main__":
    main()
