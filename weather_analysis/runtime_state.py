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
