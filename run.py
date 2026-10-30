"""
File chạy chính: mở GUI.

    python run.py              # GUI, kết nối thiết bị thật (cần Python 32-bit)
    python run.py --simulate   # GUI với thiết bị giả lập
    python run.py info --ip 192.168.1.201   # các lệnh CLI khác: xem README
"""

import sys

from zkc3.cli import main

if __name__ == "__main__":
    sys.exit(main())
