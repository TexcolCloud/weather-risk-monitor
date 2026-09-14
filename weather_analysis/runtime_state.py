"""Process coordination and persisted execution state for the daemon."""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from .paths import APP_DATA_DIR


RUNTIME_DIR = APP_DATA_DIR / "runtime"
STATE_PATH = RUNTIME_DIR / "weather-analysis-state.json"
LOCK_PATH = RUNTIME_DIR / "weather-analysis.lock"


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as file:
            temporary = Path(file.name)
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink(missing_ok=True)


class RunStateStore:
    def __init__(self, path: Path = STATE_PATH):
        self.path = path

    def is_completed(self, kind: str, target: datetime) -> bool:
        completed = _read_json(self.path).get("completed", {})
        return completed.get(kind) == target.isoformat()

    def mark_completed(self, kind: str, target: datetime) -> None:
        state = _read_json(self.path)
        completed = state.setdefault("completed", {})
        completed[kind] = target.isoformat()
        _write_json(self.path, state)


def _process_is_running(pid: int) -> bool:
    if isinstance(pid, bool) or pid <= 0:
        return False
    if os.name == "nt":
        # os.kill(pid, 0) sends CTRL_C_EVENT on Windows and can interrupt the
        # shared console, including the terminal or agent running this program.
        import ctypes
        from ctypes import wintypes

        if pid > 0xFFFFFFFF:
            return False
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            error = ctypes.get_last_error()
            if error == 87:  # ERROR_INVALID_PARAMETER: no process for this PID
                return False
            if error == 5:  # ERROR_ACCESS_DENIED: preserve the existing lock
                return True
            raise ctypes.WinError(error)
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                raise ctypes.WinError(ctypes.get_last_error())
            return exit_code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


class DaemonLock:
    """Exclusive lock that also recovers a lock left by a terminated process."""

    def __init__(self, path: Path = LOCK_PATH):
        self.path = path
        self._acquired = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                record = _read_json(self.path)
                pid = record.get("pid")
                if isinstance(pid, int) and _process_is_running(pid):
                    raise RuntimeError(f"守护进程已在运行，PID={pid}")
                self.path.unlink(missing_ok=True)
                continue
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump({"pid": os.getpid(), "startedAt": datetime.now().isoformat()}, file)
            self._acquired = True
            return
        raise RuntimeError("无法获取守护进程锁")

    def release(self) -> None:
        if self._acquired:
            self.path.unlink(missing_ok=True)
            self._acquired = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.release()
