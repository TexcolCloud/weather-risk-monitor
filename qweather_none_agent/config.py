
import json
from pathlib import Path

QWEATHER_API_KEY = ""

FORECAST_DAYS = "7d"
HOURLY_HOURS = "168"
QWEATHER_BASE_URL = "https://devapi.qweather.com/v7/weather"

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

with open(_DATA_DIR / "rooms.json", encoding="utf-8") as f:
    SITES = json.load(f)
