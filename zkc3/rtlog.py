"""
Phân tích chuỗi trả về từ GetRTLog. Mỗi dòng có dạng:
  time,pin,cardno,doorid,eventtype,inoutstate,verifytype
Dòng có eventtype = 255 là bản ghi trạng thái:
  time,doorsensor,alarm,?,255,?,?
Đầu đọc QR (vd. QR500/QR600 qua Wiegand hoặc RS485) gửi nội dung mã lên
controller như một số thẻ, nên mã QR nằm ở trường cardno.
"""

from __future__ import annotations

from datetime import datetime

from .models import AccessEvent, DoorStatus

_GRANTED = {0, 1, 3, 14, 15, 16, 17, 18, 19}

EVENT_NAMES = {
    0: "Quét thẻ/QR hợp lệ",
    1: "Hợp lệ (khung giờ mở thường trực)",
    2: "Thẻ đầu tiên mở cửa",
    3: "Đa thẻ mở cửa",
    4: "Mật khẩu khẩn cấp",
    5: "Mở trong khung giờ thường trực",
    6: "Kích hoạt liên động",
    7: "Huỷ báo động",
    8: "Mở cửa từ xa",
    9: "Đóng cửa từ xa",
    20: "Quét quá nhanh",
    21: "Cửa ngoài khung giờ hoạt động",
    22: "Ngoài khung giờ",
    23: "Từ chối truy cập",
    24: "Anti-passback",
    25: "Interlock",
    26: "Chờ xác thực đa thẻ",
    27: "Thẻ chưa đăng ký",
    28: "Cửa mở quá thời gian",
    29: "Thẻ hết hạn",
    30: "Sai mật khẩu",
    36: "Sai chế độ xác thực",
    101: "Báo động cưỡng ép",
    102: "Cửa bị mở cưỡng bức",
    200: "Cửa đã mở",
    201: "Cửa đã đóng",
    202: "Nút Exit mở cửa",
    204: "Kết thúc khung giờ thường trực",
    205: "Mở thường trực từ xa",
    206: "Thiết bị khởi động",
    220: "Aux input ngắt",
    221: "Aux input nối",
}


def event_name(t: int) -> str:
    return EVENT_NAMES.get(t, f"Sự kiện {t}")


def parse(raw: str) -> tuple[list[AccessEvent], list[DoorStatus]]:
    events: list[AccessEvent] = []
    statuses: list[DoorStatus] = []
    for line in raw.splitlines():
        f = line.split(",")
        if len(f) < 7:
            continue
        try:
            time = datetime.strptime(f[0].strip(), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            time = datetime.now()

        event_type = _to_int(f[4])
        if event_type == 255:
            statuses.append(DoorStatus(time=time, door1_sensor=_to_int(f[1]) & 0xFF, alarm=_to_int(f[2])))
            continue

        events.append(AccessEvent(
            time=time,
            pin=f[1].strip(),
            code=f[2].strip(),
            door=_to_int(f[3]),
            event_type=event_type,
            event_name=event_name(event_type),
            direction={0: "Vào", 1: "Ra"}.get(_to_int(f[5]), "—"),
            verify_type=_to_int(f[6]),
            granted=event_type in _GRANTED,
            raw=line,
        ))
    return events, statuses


def is_scan_event(e: AccessEvent) -> bool:
    """Sự kiện có ý nghĩa với việc quét QR/thẻ (bỏ qua các sự kiện cửa đóng/mở, aux input...)."""
    return bool(e.code) and e.code != "0"


def _to_int(s: str) -> int:
    try:
        return int(s.strip())
    except ValueError:
        return 0
