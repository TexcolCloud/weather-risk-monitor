import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from weather_analysis.runtime_state import DaemonLock, RunStateStore


class RuntimeStateTest(unittest.TestCase):
    def test_run_state_persists_completed_target(self):
        target = datetime(2026, 7, 14, 8, 10, tzinfo=ZoneInfo("Asia/Shanghai"))
        with tempfile.TemporaryDirectory() as temporary:
            store = RunStateStore(Path(temporary) / "state.json")
            self.assertFalse(store.is_completed("full", target))
            store.mark_completed("full", target)
            self.assertTrue(store.is_completed("full", target))

    def test_daemon_lock_rejects_another_live_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "daemon.lock"
            with DaemonLock(path):
                with self.assertRaises(RuntimeError):
                    DaemonLock(path).acquire()
