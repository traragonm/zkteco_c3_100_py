"""Binding ctypes cho ZKTeco PullSDK (plcommpro.dll) dùng với dòng C3/inBio.

Các hàm trong DLL KHÔNG thread-safe: mọi lời gọi phải được tuần tự hoá
(xem :class:`zkc3.controller.C3Controller`).
"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

DLL_NAME = "plcommpro.dll"

# Chuỗi tham số gửi vào DLL là ANSI (giống CharSet.Ansi bên C#).
_ENCODING = "mbcs" if sys.platform == "win32" else "utf-8"

ERROR_DESCRIPTIONS = {
    -1: "lệnh gửi lỗi",
    -2: "timeout / không phản hồi",
    -3: "bộ đệm không đủ",
    -4: "giải nén lỗi",
    -5: "độ dài dữ liệu sai",
    -6: "lỗi giải nén dữ liệu",
    -7: "lệnh lặp lại",
    -8: "kết nối chưa được xác thực",
    -9: "lỗi dữ liệu",
    -10: "kiểm tra CRC sai",
    -11: "dữ liệu không phù hợp",
    -12: "sai mật khẩu kết nối (comm key)",
    -13: "dữ liệu nhận được sai",
    -14: "thiết bị bận",
    -15: "tham số sai",
    -307: "không kết nối được (sai IP/cổng hoặc mạng)",
}


def describe_error(code: int) -> str:
    return ERROR_DESCRIPTIONS.get(code, "không xác định")


class SdkLoadError(RuntimeError):
    """Không tải được plcommpro.dll (thiếu DLL, sai kiến trúc, không phải Windows...)."""


def find_sdk_dir() -> Path | None:
    """Tìm thư mục chứa plcommpro.dll: $ZKC3_SDK_DIR, ./sdk, <project>/sdk, thư mục hiện tại."""
    candidates = []
    if env := os.environ.get("ZKC3_SDK_DIR"):
        candidates.append(Path(env))
    candidates += [Path.cwd() / "sdk", Path(__file__).resolve().parent.parent / "sdk", Path.cwd()]
    for d in candidates:
        if (d / DLL_NAME).is_file():
            return d.resolve()
    return None


def _encode(s: str) -> bytes:
    return s.encode(_ENCODING, errors="replace")


def _decode(b: bytes) -> str:
    return b.decode("utf-8", errors="replace")


class PullSdk:
    """Gói các hàm của plcommpro.dll. Handle là số nguyên (0 = không hợp lệ)."""

    def __init__(self, sdk_dir: str | os.PathLike | None = None):
        if sys.platform != "win32":
            raise SdkLoadError("PullSDK chỉ chạy trên Windows.")

        directory = Path(sdk_dir) if sdk_dir else find_sdk_dir()
        if directory is None:
            raise SdkLoadError(
                f"Không tìm thấy {DLL_NAME}. Chép bộ DLL PullSDK vào thư mục 'sdk' "
                "hoặc đặt biến môi trường ZKC3_SDK_DIR.")

        # Để Windows tìm được các DLL phụ thuộc (plcomms.dll, pltcpcomm.dll...).
        self._dll_dir = os.add_dll_directory(str(directory))
        try:
            dll = ctypes.WinDLL(str(directory / DLL_NAME))
        except OSError as ex:
            self._dll_dir.close()
            if getattr(ex, "winerror", None) == 193:
                bits = "64" if sys.maxsize > 2**32 else "32"
                raise SdkLoadError(
                    f"Sai kiến trúc DLL: Python đang chạy {bits}-bit. "
                    "PullSDK 32-bit cần Python 32-bit (x86), PullSDK 64-bit cần Python 64-bit.") from ex
            raise SdkLoadError(f"Không tải được {DLL_NAME} hoặc DLL phụ thuộc: {ex}") from ex

        self.directory = directory
        self._dll = dll
        h, c_int, c_char_p = ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p

        self._proto("Connect", h, [c_char_p])
        self._proto("Disconnect", None, [h])
        self._proto("GetDeviceParam", c_int, [h, c_char_p, c_int, c_char_p])
        self._proto("SetDeviceParam", c_int, [h, c_char_p])
        self._proto("ControlDevice", c_int, [h, c_int, c_int, c_int, c_int, c_int, c_char_p])
        self._proto("GetRTLog", c_int, [h, c_char_p, c_int])
        self._proto("GetDeviceData", c_int, [h, c_char_p, c_int, c_char_p, c_char_p, c_char_p, c_char_p])
        self._proto("SetDeviceData", c_int, [h, c_char_p, c_char_p, c_char_p])
        self._proto("DeleteDeviceData", c_int, [h, c_char_p, c_char_p, c_char_p])
        self._proto("GetDeviceDataCount", c_int, [h, c_char_p, c_char_p, c_char_p])
        self._proto("PullLastError", c_int, [])

    def _proto(self, name: str, restype, argtypes) -> None:
        fn = getattr(self._dll, name)
        fn.restype = restype
        fn.argtypes = argtypes

    # ------------------------------------------------------------ kết nối

    def connect(self, parameters: str) -> int:
        """Ví dụ: ``protocol=TCP,ipaddress=192.168.1.201,port=4370,timeout=4000,passwd=``."""
        return self._dll.Connect(_encode(parameters)) or 0

    def disconnect(self, handle: int) -> None:
        self._dll.Disconnect(handle)

    def pull_last_error(self) -> int:
        return self._dll.PullLastError()

    # ------------------------------------------------------------ tham số thiết bị

    def get_device_param(self, handle: int, items: str, buffer_size: int = 4096) -> tuple[int, str]:
        """``items`` dạng ``"~SerialNumber,FirmVer,LockCount"``; trả về (ret, ``"k=v,k=v"``)."""
        buf = ctypes.create_string_buffer(buffer_size)
        ret = self._dll.GetDeviceParam(handle, buf, buffer_size, _encode(items))
        return ret, _decode(buf.value)

    def set_device_param(self, handle: int, item_values: str) -> int:
        """``item_values`` dạng ``"DateTime=123456,Door1Drivertime=5"``."""
        return self._dll.SetDeviceParam(handle, _encode(item_values))

    def control_device(self, handle: int, operation_id: int, param1: int, param2: int, param3: int,
                       param4: int = 0, options: str = "") -> int:
        """
        operation_id: 1 = điều khiển output, 2 = huỷ báo động, 3 = khởi động lại.
        param1: số cửa (hoặc số aux output). param2: 1 = khoá cửa, 2 = aux output.
        param3: 0 = đóng, 1..254 = mở N giây, 255 = mở thường trực.
        """
        return self._dll.ControlDevice(handle, operation_id, param1, param2, param3, param4, _encode(options))

    # ------------------------------------------------------------ sự kiện thời gian thực

    def get_rt_log(self, handle: int, buffer: ctypes.Array) -> tuple[int, str]:
        """Đọc sự kiện mới. ``buffer`` tạo bằng ``ctypes.create_string_buffer`` để dùng lại giữa các lần poll."""
        ctypes.memset(buffer, 0, len(buffer))
        ret = self._dll.GetRTLog(handle, buffer, len(buffer))
        return ret, _decode(buffer.value)

    # ------------------------------------------------------------ bảng dữ liệu (user, userauthorize, transaction...)

    def get_device_data(self, handle: int, table: str, fields: str = "*", filter: str = "",
                        options: str = "", buffer_size: int = 4 * 1024 * 1024) -> tuple[int, str]:
        """Trả về (số bản ghi hoặc mã lỗi, CSV có dòng tiêu đề)."""
        buf = ctypes.create_string_buffer(buffer_size)
        ret = self._dll.GetDeviceData(handle, buf, buffer_size, _encode(table), _encode(fields),
                                      _encode(filter), _encode(options))
        return ret, _decode(buf.value)

    def set_device_data(self, handle: int, table: str, data: str, options: str = "") -> int:
        """``data`` dạng ``"Pin=1\\tCardNo=123\\tName=A\\r\\nPin=2\\t..."``."""
        return self._dll.SetDeviceData(handle, _encode(table), _encode(data), _encode(options))

    def delete_device_data(self, handle: int, table: str, data: str, options: str = "") -> int:
        return self._dll.DeleteDeviceData(handle, _encode(table), _encode(data), _encode(options))

    def get_device_data_count(self, handle: int, table: str, filter: str = "", options: str = "") -> int:
        return self._dll.GetDeviceDataCount(handle, _encode(table), _encode(filter), _encode(options))
