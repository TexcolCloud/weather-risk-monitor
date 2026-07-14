
import json
import shutil
import time
from pathlib import Path

_CACHE_DIR = Path(__file__).parent / "data" / ".cache"

DAILY_TTL = 3 * 60 * 60       # 3 hours
HOURLY_TTL = 45 * 60          # 45 minutes


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
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({"_ct": time.time(), "_pl": payload}, f, ensure_ascii=False)
    except Exception:
        pass


def clear():
    if _CACHE_DIR.exists():
        shutil.rmtree(str(_CACHE_DIR))
