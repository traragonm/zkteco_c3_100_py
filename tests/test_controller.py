import tempfile
import threading
import unittest

from zkc3 import AppLogger, C3Controller, ConnectionSettings, ConnectionState
from zkc3.simulator import FakePullSdk


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = AppLogger(self.tmp.name)
        self.sdk = FakePullSdk(scan_interval=0.05, seed=1)
        self.device = C3Controller(self.log, lambda: self.sdk)

    def tearDown(self):
        self.device.disconnect()
        self.device.close()
        self.tmp.cleanup()

    def test_connect_info_door_and_events(self):
        got_events = threading.Event()
        states = []
        self.device.state_changed.connect(states.append)
        self.device.events_received.connect(lambda _: got_events.set())

        self.assertTrue(self.device.connect(ConnectionSettings("127.0.0.1", poll_interval_ms=20)))
        self.assertEqual(states, [ConnectionState.CONNECTING, ConnectionState.CONNECTED])

        info = self.device.refresh_device_info()
        self.assertEqual((info.serial, info.lock_count), ("SIM-C3100-0001", 1))
        self.assertIsNotNone(info.device_time)

        self.assertTrue(self.device.set_door(1, 5))
        self.assertTrue(self.device.sync_time())
        self.assertTrue(got_events.wait(3))

        self.device.disconnect()
        self.assertEqual(self.device.state, ConnectionState.DISCONNECTED)
        self.assertFalse(self.device.set_door(1, 5))

    def test_connect_failure(self):
        self.assertFalse(self.device.connect(ConnectionSettings("")))
        self.assertEqual(self.device.state, ConnectionState.DISCONNECTED)

    def test_lost_connection_without_auto_reconnect(self):
        stopped = threading.Event()
        self.device.state_changed.connect(lambda s: s == ConnectionState.DISCONNECTED and stopped.set())
        self.device.connect(ConnectionSettings("127.0.0.1", poll_interval_ms=10, auto_reconnect=False))
        self.sdk._handles.clear()  # giả lập thiết bị rớt mạng
        self.assertTrue(stopped.wait(3))

    def test_tables(self):
        self.device.connect(ConnectionSettings("127.0.0.1"))
        self.assertTrue(self.device.set_table("user", [{"Pin": "2", "CardNo": "999", "Name": "B"}]))
        pins = {r["Pin"] for r in self.device.get_table("user")}
        self.assertEqual(pins, {"1", "2"})
        self.assertTrue(self.device.delete_table("user", [{"Pin": "2"}]))
        self.assertEqual([r["Pin"] for r in self.device.get_table("user")], ["1"])


if __name__ == "__main__":
    unittest.main()
