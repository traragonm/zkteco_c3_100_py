# ZKTeco C3-100 — Python

Bản Python của [ZKTeco C3-100 Manager](https://github.com/traragonm/zkteco_c3_100): kết nối bộ điều khiển kiểm soát ra vào **ZKTeco C3-100** qua PullSDK (`plcommpro.dll`), ghi lại sự kiện quét **QR / thẻ**, xác thực mã quét qua **API của bạn** (hoặc hỏi người vận hành) rồi mở cửa, và lưu log kết nối.

Project gồm 3 phần dùng chung một lõi:

| Phần | Dùng khi |
|---|---|
| **Thư viện `zkc3`** | Viết script/dịch vụ riêng: kết nối, đọc sự kiện, mở cửa, đọc/ghi bảng `user`... |
| **GUI** (tkinter) | Giao diện giống bản WinForms: theo dõi lượt quét, Verify API, popup mở cửa, xem lại mã QR |
| **CLI** | Thao tác nhanh từ dòng lệnh: `info`, `open`, `close`, `sync-time`, `monitor`, `table` |

Lõi chỉ dùng thư viện chuẩn của Python. `qrcode[pil]` là tuỳ chọn, chỉ để xem/lưu ảnh QR trong GUI.

## Yêu cầu

| Thành phần | Ghi chú |
|---|---|
| Windows 10/11 | PullSDK chỉ có cho Windows |
| **Python 3.10+ cùng kiến trúc với PullSDK** | PullSDK phổ biến là **32-bit**, nên cần **Python 32-bit (x86)**. Xem bên dưới |
| PullSDK của ZKTeco | Không có trong repo, xem bước 2 |
| ZKTeco C3-100 + đầu đọc QR | Ví dụ QR500/QR600 nối vào controller qua Wiegand/RS485 |

> **Quan trọng: kiến trúc Python.** Python 64-bit không nạp được DLL 32-bit (và ngược lại). Bộ DLL trong project C# là bản 32-bit (`PE32, Intel i386`).
> Cài Python **Windows installer (32-bit)** từ https://www.python.org/downloads/windows/, hoặc dùng Python install manager: `py install 3.13-32`, rồi chạy bằng `py -V:3.13-32 -m zkc3`.
> Kiểm tra: `python -c "import sys; print(sys.maxsize > 2**32)"` in `False` là 32-bit.
> Sai kiến trúc thì app báo: *"Sai kiến trúc DLL: Python đang chạy 64-bit..."*.

## Cài đặt

1. **Tạo môi trường ảo bằng Python 32-bit** (khuyên dùng)
   ```
   cd zkteco_c3_100_py
   py -V:3.13-32 -m venv .venv32
   .venv32\Scripts\activate
   pip install -r requirements.txt      # tuỳ chọn: ảnh QR
   ```
2. **Chép DLL của PullSDK** vào thư mục `sdk\`: `plcommpro.dll`, `plcomms.dll`, `plrscagent.dll`, `plrscomm.dll`, `pltcpcomm.dll`, `plusbcomm.dll` (và `rscagent.dll`, `rscomm.dll`, `tcpcomm.dll`, `usbcomm.dll`, `usbstd.dll` nếu bộ SDK của bạn có).
   Có thể đặt DLL ở chỗ khác rồi trỏ tới bằng biến môi trường `ZKC3_SDK_DIR` hoặc tham số `--sdk-dir`.
   > DLL là phần mềm của ZKTeco nên `sdk/*.dll` nằm trong `.gitignore`.
3. **Chạy**
   ```
   python -m zkc3                 # mở GUI
   python -m zkc3 --simulate      # mở GUI với thiết bị giả lập (không cần DLL / thiết bị)
   ```
   Hoặc `pip install -e .` để có lệnh `zkc3`.

## GUI

Cách dùng giống hệt bản WinForms:

1. Card **Kết nối**: nhập IP (cổng mặc định `4370`), mật khẩu (comm key, nếu có), chu kỳ đọc (500 ms là hợp lý), bật **Tự kết nối lại** nếu app chạy liên tục. Bấm **Kết nối** (**F5**), ngắt bằng **Shift+F5**.
2. Tab **Sự kiện quét QR**: mỗi lượt quét một dòng, nền xanh = mở cửa, đỏ = từ chối, vàng = đang chờ xác thực. Nhấp đúp (hoặc Enter) để xem lại mã QR, sao chép mã, lưu ảnh PNG 800 px.
3. **Xuất CSV** (**Ctrl+S**) danh sách đang hiển thị; **Xoá** chỉ xoá trên màn hình.
4. Tab **Log kết nối**: log có màu theo cấp độ, tick **Hiện DEBUG** để xem dữ liệu RTLog thô.
5. **Điều khiển cửa**: mở N giây (1–254) hoặc đóng ngay. **Đồng bộ giờ PC → thiết bị** ở card Thiết bị.

### Xác thực QR / Card

Mở **Cài đặt xác thực** trên header.

> Để app được quyết định mở cửa, mã QR/thẻ **không được đăng ký** trên controller. Khi đó controller báo "Thẻ chưa đăng ký", app gọi API, và nếu được phép thì gửi lệnh mở cửa. Mã đã đăng ký thì controller tự mở cửa.

| Trường | Mô tả |
|---|---|
| Bật xác thực qua API | Tắt (hoặc URL trống) thì app hỏi người vận hành bằng popup |
| URL | Ví dụ `https://api.example.com/access/verify`, dùng được biến: `...?code={code}` |
| Phương thức | `POST`, `PUT` hoặc `GET` |
| Headers | Mỗi dòng `Tên: Giá trị`, ví dụ `Authorization: Bearer xxx` |
| Body data | Template nội dung gửi đi (bỏ trống nếu GET) |
| Timeout (ms) | Quá thời gian này thì coi là API lỗi |
| Trường kết quả JSON | Mặc định `allow`; hỗ trợ trường lồng như `data.allow` |
| Khi API lỗi | Hỏi người vận hành (popup), hoặc Từ chối |
| Bỏ qua lượt quét controller đã cho phép | Không gọi API cho mã đã đăng ký trên thiết bị |
| Mở cửa / Bỏ quét trùng / Popup tự đóng (giây) | Như bản WinForms |

**Biến**: `{code}` `{pin}` `{door}` `{direction}` (`in`/`out`) `{eventType}` `{eventName}` `{time}` (`2026-10-29T09:14:31`) `{deviceSerial}`. Trong URL giá trị được URL-encode, trong body JSON được escape theo JSON.

**API cần trả về** HTTP 2xx kèm JSON:
```json
{ "allow": true, "message": "Khách hẹn 09:30", "openSeconds": 5 }
```
`allow` bắt buộc (`true`/`false`, `1`/`0`, `"true"`/`"false"`); `message` và `openSeconds` tuỳ chọn. Bấm **Kiểm tra API** để gửi thử mã `TEST-QR-0001`.

Popup thủ công: **Enter** mở cửa, **Esc** không mở, hết giờ đếm ngược thì tự từ chối. Nhiều lượt quét cùng lúc thì popup lần lượt hiện từng cái.

## CLI

```
python -m zkc3 info      --ip 192.168.1.201
python -m zkc3 open      --ip 192.168.1.201 --door 1 --seconds 5
python -m zkc3 close     --ip 192.168.1.201 --door 1
python -m zkc3 sync-time --ip 192.168.1.201
python -m zkc3 monitor   --ip 192.168.1.201 --poll 500       # Ctrl+C để dừng
python -m zkc3 table user --ip 192.168.1.201 --fields CardNo,Pin,Name
```

Tuỳ chọn chung (đặt **sau** tên lệnh): `--ip`, `--port`, `--timeout`, `--password`, `--sdk-dir`, `--simulate`, `-v` (in cả DEBUG). Không truyền `--ip` thì dùng IP đã lưu trong `settings.json`. Mã thoát `0` = thành công, `1` = lỗi.

## Dùng như thư viện

```python
from zkc3 import AppLogger, C3Controller, ConnectionSettings
from zkc3.rtlog import is_scan_event

log = AppLogger("logs")
device = C3Controller(log)                 # tìm plcommpro.dll trong ./sdk hoặc $ZKC3_SDK_DIR

def on_events(events):                     # gọi từ thread polling
    for e in events:
        if is_scan_event(e) and not e.granted and e.code.startswith("QR-"):
            device.set_door(e.door or 1, 5)

device.events_received.connect(on_events)
with device:                               # tự ngắt kết nối khi ra khỏi khối
    device.connect(ConnectionSettings("192.168.1.201", password=""))
    print(device.refresh_device_info())
    print(device.get_table("user", "CardNo,Pin,Name"))
    device.set_table("user", [{"Pin": 2, "CardNo": 12345678, "Name": "B"}])
    ...
```

Ví dụ đầy đủ: [examples/basic_usage.py](examples/basic_usage.py) (`python examples/basic_usage.py --simulate`).

| API | Ghi chú |
|---|---|
| `connect(settings)` / `disconnect()` | Chặn tới khi xong. Kết nối thành công thì tự bắt đầu polling `GetRTLog` |
| `refresh_device_info()` | Serial, firmware, số cửa, giờ thiết bị |
| `sync_time()` | Đồng bộ giờ PC → thiết bị |
| `set_door(door, seconds)` | `0` đóng, `1..254` mở N giây, `255` mở thường trực |
| `get_table` / `set_table` / `delete_table` | `GetDeviceData` / `SetDeviceData` / `DeleteDeviceData` (bảng `user`, `userauthorize`, `transaction`...) |
| `state_changed`, `events_received`, `status_received`, `device_info_received` | Signal; đăng ký bằng `.connect(fn)`. Lỗi trong callback được ghi log, không làm dừng polling |

Mọi lời gọi DLL đi qua một khoá duy nhất vì `plcommpro.dll` không thread-safe, nên gọi `set_door` từ callback hay từ thread khác đều an toàn. Muốn gọi thẳng DLL thì dùng `zkc3.sdk.PullSdk`.

## File dữ liệu

Nằm trong thư mục hiện tại (hoặc `$ZKC3_HOME` nếu đặt):

| File | Nội dung |
|---|---|
| `settings.json` | Thông số kết nối và cấu hình Verify API (Headers lưu dạng chữ thường, có thể chứa token) |
| `logs/connection_yyyy-MM-dd.log` | Log kết nối, lỗi SDK, kết quả gọi API, RTLog thô (DEBUG) |
| `logs/events_yyyy-MM-dd.csv` | Mỗi lượt quét một dòng (UTF-8 có BOM, mở được bằng Excel) |

`settings.json` và `logs/` đã có trong `.gitignore`. File log và CSV chứa mã thẻ/QR của người dùng, hãy bảo quản theo quy định nội bộ.

## Xử lý sự cố

| Lỗi | Cách xử lý |
|---|---|
| `Sai kiến trúc DLL: Python đang chạy 64-bit` | Chạy bằng Python 32-bit (xem phần Yêu cầu) |
| `Không tìm thấy plcommpro.dll` | Chép DLL vào `sdk\` hoặc đặt `ZKC3_SDK_DIR` |
| `Không tải được plcommpro.dll hoặc DLL phụ thuộc` | Thiếu DLL phụ (chép **đủ** bộ SDK), hoặc thiếu Visual C++ Redistributable x86 |
| Connect lỗi `-307` | Sai IP/cổng, hoặc PC không cùng mạng với controller |
| Connect lỗi `-12` | Sai mật khẩu kết nối (comm key) |
| Connect lỗi `-2` | Timeout: thiết bị không phản hồi, thử tăng Timeout |
| Không thấy ảnh QR trong popup | `pip install qrcode[pil]` |

## Phát triển

```
python -m unittest discover -s tests -v
```

Test chạy bằng thiết bị giả lập và một HTTP server cục bộ, không cần DLL hay thiết bị thật.

```
zkc3/
├─ sdk.py             Binding ctypes cho plcommpro.dll (Connect, GetRTLog, ControlDevice, GetDeviceData...)
├─ controller.py      Kết nối, polling GetRTLog, tự kết nối lại, điều khiển cửa, bảng dữ liệu
├─ rtlog.py           Phân tích dữ liệu RTLog, tên sự kiện
├─ device_time.py     Mã hoá / giải mã giờ kiểu C3
├─ verify_api.py      Gọi Verify API theo template URL / Headers / Body
├─ simulator.py       Thiết bị giả lập (--simulate, test)
├─ logger.py          Log kết nối ra file + listener
├─ csv_writer.py      Ghi / xuất CSV sự kiện
├─ settings.py        Lưu settings.json
├─ cli.py             Dòng lệnh
└─ gui/               Cửa sổ chính, cài đặt xác thực, popup mở cửa, xem QR
sdk/                  ← chép DLL PullSDK vào đây
```
