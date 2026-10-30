"""Gọi Verify API theo cấu hình URL / Headers / Body template (chỉ dùng thư viện chuẩn)."""

from __future__ import annotations

import http.client
import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Iterator, Mapping

from .models import AccessEvent, VerifyApiSettings

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


@dataclass(frozen=True)
class VerifyResult:
    success: bool
    allow: bool
    message: str | None
    open_seconds: int | None
    error: str | None
    status_code: int
    elapsed_ms: int
    response_text: str


def verify(s: VerifyApiSettings, e: AccessEvent, device_serial: str) -> VerifyResult:
    started = time.monotonic()
    elapsed = lambda: int((time.monotonic() - started) * 1000)  # noqa: E731

    def fail(error: str, status: int = 0, text: str = "") -> VerifyResult:
        return VerifyResult(False, False, None, None, error, status, elapsed(), text)

    try:
        req = build_request(s, variables(e, device_serial))
        with urllib.request.urlopen(req, timeout=max(500, s.timeout_ms) / 1000) as resp:
            status = resp.status
            text = resp.read().decode(resp.headers.get_content_charset() or "utf-8", errors="replace")
    except urllib.error.HTTPError as ex:
        with ex:
            text = ex.read().decode("utf-8", errors="replace") if ex.fp else ""
        return fail(f"HTTP {ex.code} {ex.reason}", ex.code, text)
    except (TimeoutError, socket.timeout):
        return fail(f"Timeout sau {s.timeout_ms} ms")
    except urllib.error.URLError as ex:
        if isinstance(ex.reason, (TimeoutError, socket.timeout)):
            return fail(f"Timeout sau {s.timeout_ms} ms")
        return fail(str(ex.reason))
    except (ValueError, OSError, http.client.HTTPException) as ex:
        return fail(str(ex))

    if not 200 <= status < 300:
        return fail(f"HTTP {status}", status, text)
    return _parse_response(s.result_field, text, status, elapsed(), fail)


def build_request(s: VerifyApiSettings, vars: Mapping[str, str]) -> urllib.request.Request:
    url = fill(s.url.strip(), vars, lambda v: urllib.parse.quote(v, safe=""))
    method = (s.method or "POST").strip().upper()

    headers: dict[str, str] = {}
    content_type = None
    for name, value in parse_headers(s.headers):
        v = fill(value, vars, lambda x: x)
        if name.lower() == "content-type":
            content_type = v
        else:
            headers[name] = v

    data = None
    if method != "GET" and s.body.strip():
        stripped = s.body.lstrip()
        is_json = "json" in content_type.lower() if content_type else stripped.startswith(("{", "["))
        # Trong body JSON, giá trị được escape để mã QR chứa dấu " hoặc \ không làm hỏng JSON.
        body = fill(s.body, vars, json_escape if is_json else (lambda x: x))
        data = body.encode("utf-8")
        ct = content_type or ("application/json" if is_json else "text/plain")
        if "charset" not in ct.lower():
            ct += "; charset=utf-8"
        headers["Content-Type"] = ct

    return urllib.request.Request(url, data=data, headers=headers, method=method)


def variables(e: AccessEvent, device_serial: str) -> dict[str, str]:
    return {
        "code": e.code,
        "pin": e.pin,
        "door": str(e.door),
        "direction": "out" if e.direction == "Ra" else "in",
        "eventType": str(e.event_type),
        "eventName": e.event_name,
        "time": f"{e.time:%Y-%m-%dT%H:%M:%S}",
        "deviceSerial": device_serial,
    }


def fill(template: str, vars: Mapping[str, str], encode: Callable[[str], str]) -> str:
    """Thay {biến} (không phân biệt hoa thường); biến không biết giữ nguyên để không phá JSON có dấu ngoặc nhọn."""
    lower = {k.lower(): v for k, v in vars.items()}

    def repl(m: re.Match) -> str:
        v = lower.get(m.group(1).lower())
        return m.group(0) if v is None else encode(v)

    return _PLACEHOLDER.sub(repl, template)


def parse_headers(text: str) -> Iterator[tuple[str, str]]:
    for raw in text.split("\n"):
        name, sep, value = raw.strip().partition(":")
        if sep and name.strip():
            yield name.strip(), value.strip()


def json_escape(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)[1:-1]


def _parse_response(field: str, text: str, status: int, elapsed_ms: int, fail) -> VerifyResult:
    try:
        doc = json.loads(text)
    except ValueError:
        return fail("Response không phải JSON", status, text)

    found, value = _get_path(doc, field)
    if not found:
        return fail(f'Không có trường "{field}" trong response', status, text)
    ok, allow = _to_bool(value)
    if not ok:
        return fail(f'Trường "{field}" không phải true/false', status, text)

    _, message = _get_path(doc, "message")
    _, open_seconds = _get_path(doc, "openSeconds")
    return VerifyResult(
        True, allow,
        message if isinstance(message, str) else None,
        open_seconds if isinstance(open_seconds, int) and not isinstance(open_seconds, bool) else None,
        None, status, elapsed_ms, text)


def _get_path(root, path: str) -> tuple[bool, object]:
    value = root
    for part in (p.strip() for p in path.split(".")):
        if not part:
            continue
        if not isinstance(value, dict) or part not in value:
            return False, None
        value = value[part]
    return True, value


def _to_bool(v) -> tuple[bool, bool]:
    if isinstance(v, bool):
        return True, v
    if isinstance(v, int):
        return True, v != 0
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "1", "yes", "allow", "ok"):
            return True, True
        if s in ("false", "0", "no", "deny"):
            return True, False
    return False, False
