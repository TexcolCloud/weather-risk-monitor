import json
import math
import os
from pathlib import Path

from dotenv import load_dotenv

from .paths import PROJECT_ROOT


load_dotenv(PROJECT_ROOT / ".env")

QWEATHER_API_KEY = os.environ.get("QWEATHER_API_KEY", "")

HOURLY_HOURS = "168"
QWEATHER_BASE_URL = "https://devapi.qweather.com/v7/weather"
QWEATHER_WARNING_URL = "https://devapi.qweather.com/v7/warning/now"

_DATA_DIR = Path(__file__).resolve().parent / "data"

def load_sites(path=None):
    """Load local site configuration; bundled coordinates are synthetic examples."""
    selected = Path(path or os.environ.get("WEATHER_ANALYSIS_SITES_FILE") or _DATA_DIR / "sites.example.json")
    if not selected.is_absolute():
        selected = PROJECT_ROOT / selected
    with selected.open(encoding="utf-8") as stream:
        sites = json.load(stream)
    if not isinstance(sites, list) or not sites:
        raise ValueError("Site configuration must be a non-empty JSON array")
    for index, site in enumerate(sites):
        if not isinstance(site, dict) or any(not isinstance(site.get(key), str) or not site[key].strip() for key in ("name", "county")):
            raise ValueError(f"Site {index}: name and county must be non-empty strings")
        for key, bound in (("lon", 180), ("lat", 90)):
            value = site.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not -bound <= value <= bound:
                raise ValueError(f"Site {index}: invalid {key}")
    return sites


SITES = load_sites()
