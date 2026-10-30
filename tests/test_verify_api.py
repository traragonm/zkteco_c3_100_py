import json
import threading
import unittest
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from zkc3 import verify_api
from zkc3.models import AccessEvent, VerifyApiSettings


class _Handler(BaseHTTPRequestHandler):
    """POST /verify trả về allow theo mã; /slow ngủ quá timeout; /bad trả về HTML; /500 lỗi."""

    def log_message(self, *args):
        pass

    def _reply(self, status, body: str, ctype="application/json"):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        self.server.last = {"path": self.path, "body": payload, "auth": self.headers.get("Authorization"),
                            "ctype": self.headers.get("Content-Type")}
        if self.path == "/500":
            self._reply(500, '{"error": "boom"}')
        elif self.path == "/bad":
            self._reply(200, "<html></html>", "text/html")
        elif self.path == "/slow":
            threading.Event().wait(1.5)
            self._reply(200, '{"allow": true}')
        elif self.path == "/nested":
            self._reply(200, '{"data": {"allow": "yes"}}')
        else:
            allow = payload.get("code") == 'QR-"OK"'
            self._reply(200, json.dumps({"allow": allow, "message": "Khách hẹn", "openSeconds": 7}))

    def do_GET(self):
        self.server.last = {"path": self.path}
        self._reply(200, '{"allow": 1}')


class VerifyApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def event(self, code='QR-"OK"'):
        return AccessEvent(time=datetime(2026, 10, 29, 9, 14, 31), door=1, direction="Ra", code=code, pin="0",
                           event_type=27, event_name="Thẻ chưa đăng ký")

    def settings(self, path, **kw):
        return VerifyApiSettings(enabled=True, url=self.base + path,
                                 headers="Content-Type: application/json\nAuthorization: Bearer {deviceSerial}", **kw)

    def test_allow_with_json_escaping(self):
        r = verify_api.verify(self.settings("/verify"), self.event(), "SN1")
        self.assertTrue(r.success, r.error)
        self.assertTrue(r.allow)
        self.assertEqual((r.message, r.open_seconds), ("Khách hẹn", 7))
        last = self.server.last
        self.assertEqual(last["body"]["code"], 'QR-"OK"')
        self.assertEqual(last["body"]["door"], 1)
        self.assertEqual(last["body"]["direction"], "out")
        self.assertEqual(last["auth"], "Bearer SN1")
        self.assertIn("application/json", last["ctype"])

    def test_deny(self):
        r = verify_api.verify(self.settings("/verify"), self.event("OTHER"), "SN1")
        self.assertTrue(r.success)
        self.assertFalse(r.allow)

    def test_get_with_url_encoding(self):
        s = self.settings("/check?code={code}", method="GET")
        r = verify_api.verify(s, self.event("A B&C"), "")
        self.assertTrue(r.allow)
        self.assertEqual(self.server.last["path"], "/check?code=A%20B%26C")

    def test_nested_field(self):
        r = verify_api.verify(self.settings("/nested", result_field="data.allow"), self.event(), "")
        self.assertTrue(r.success and r.allow)

    def test_errors(self):
        self.assertEqual(verify_api.verify(self.settings("/500"), self.event(), "").status_code, 500)
        self.assertEqual(verify_api.verify(self.settings("/bad"), self.event(), "").error, "Response không phải JSON")
        missing = verify_api.verify(self.settings("/verify", result_field="ok"), self.event(), "")
        self.assertIn('"ok"', missing.error)
        slow = verify_api.verify(self.settings("/slow", timeout_ms=500), self.event(), "")
        self.assertFalse(slow.success)
        self.assertIn("Timeout", slow.error)

    def test_unknown_placeholder_kept(self):
        self.assertEqual(verify_api.fill("{a} {CODE} {x}", {"code": "1", "a": "2"}, str), "2 1 {x}")

    def test_is_configured(self):
        self.assertFalse(VerifyApiSettings(enabled=True, url="ftp://x").is_configured)
        self.assertFalse(VerifyApiSettings(enabled=False, url="https://x").is_configured)
        self.assertTrue(VerifyApiSettings(enabled=True, url=" https://api.example.com/v ").is_configured)


if __name__ == "__main__":
    unittest.main()
