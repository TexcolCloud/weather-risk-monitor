"""Isolated-console regression helper: PID probes must not interrupt the parent."""
import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from weather_analysis.runtime_state import _process_is_running


if __name__ == "__main__":
    observed = []
    ctypes.windll.kernel32.SetConsoleCtrlHandler(None, False)
    signal.signal(signal.SIGINT, lambda *_: observed.append("unexpected_interrupt"))
    if sys.argv[1] == "parent":
        child = subprocess.Popen([sys.executable, __file__, "worker"])
        try:
            child.wait(timeout=5)
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=5)
        time.sleep(0.2)
        Path(sys.argv[2]).write_text(json.dumps({"parent_signals": observed, "worker_exit": child.returncode}))
    else:
        assert _process_is_running(os.getpid())
        time.sleep(0.2)
        assert not observed, "PID lookup sent a console interrupt"
