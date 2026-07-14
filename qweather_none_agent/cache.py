
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

_DEFAULT_CACHE_ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".cache"))
_CACHE_DIR = Path(os.environ.get(
    "QWEATHER_CACHE_DIR",
    _DEFAULT_CACHE_ROOT / "qweather-none-agent",
))

DAILY_TTL = 3 * 60 * 60       # 3 hours
HOURLY_TTL = 45 * 60          # 45 minutes
WARNING_TTL = 15 * 60         # 15 minutes


def _key(lat, lon, endpoint):
    return f"{lat:.4f}_{lon:.4f}_{endpoint}".replace(".", "_")


def get(lat, lon, endpoint, ttl):
    filepath = _CACHE_DIR / f"{_key(lat, lon, endpoint)}.json"
    if not filepath.exists():
        return None
    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        if time.time() - data.get("_ct", 0) > ttl:
            return None
        return data.get("_pl")
    except Exception:
        return None


def set(lat, lon, endpoint, payload):
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    filepath = _CACHE_DIR / f"{_key(lat, lon, endpoint)}.json"
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=_CACHE_DIR, delete=False) as file:
            temporary = Path(file.name)
            json.dump({"_ct": time.time(), "_pl": payload}, file, ensure_ascii=False)
        os.replace(temporary, filepath)
    except Exception:
        pass
    finally:
        if temporary and temporary.exists():
            temporary.unlink(missing_ok=True)


def clear():
    if _CACHE_DIR.exists():
        shutil.rmtree(str(_CACHE_DIR))
