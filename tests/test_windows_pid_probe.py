import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(os.name == "nt", "Windows console regression")
class WindowsPidProbeTest(unittest.TestCase):
    def test_pid_lookup_does_not_interrupt_its_parent_console(self):
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        with tempfile.TemporaryDirectory() as directory:
            result = Path(directory) / "probe.json"
            subprocess.run(
                [sys.executable, str(Path(__file__).with_name("windows_pid_probe.py")), "parent", str(result)],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                startupinfo=startup,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=True,
            )
            value = json.loads(result.read_text())
            self.assertEqual(value, {"parent_signals": [], "worker_exit": 0})
