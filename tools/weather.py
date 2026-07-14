
import asyncio
import random
import httpx
from config import QWEATHER_API_KEY, QWEATHER_BASE_URL, FORECAST_DAYS, HOURLY_HOURS
import cache

MAX_CONCURRENT = 50
MAX_RETRIES = 3
BACKOFF_BASE = 2.0
BACKOFF_MAX_C = 8

WEATHER_KEYWORDS = {
    "thunder": ("雷", "雷暴"),
    "snow": ("雪",),
    "freezing": ("冻雨", "冰粒"),
    "hail": ("冰雹",),
    "fog": ("雾",),
    "haze": ("霾",),
    "sand": ("沙尘暴", "沙尘", "扬沙", "浮尘"),
}

WARNING_KEYS = [
    "hasThunder", "hasSnow", "hasFreezing", "hasHail",
    "hasFog", "hasHaze", "hasSand",
]

_SEVERE_KEYS = {"hasHail", "hasFreezing", "hasSnow"}


def _backoff_delay(c):
    c = min(c, BACKOFF_MAX_C)
    base = BACKOFF_BASE ** c
    jitter = random.randint(0, (2 ** c) - 1) if c > 0 else 0
    return base + jitter


def _safe_int(val, default=0):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _safe_float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


SEVERE_KEYS = ["hasHail", "hasFreezing", "hasSnow"]


class WeatherTool:

    @staticmethod
    def _loc(c):
        lat = c.get("lat", 0)
        lon = c.get("lon", 0)
        return f"{lon:.2f},{lat:.2f}"

    @staticmethod
    async def _fetch(client, sem, url, params, lat, lon, endpoint, ttl):
        cached = cache.get(lat, lon, endpoint, ttl)
        if cached is not None:
            return cached

        consecutive = 0
        for _ in range(MAX_RETRIES):
            async with sem:
                try:
                    resp = await client.get(url, params=params, timeout=10)
                    code = resp.status_code

                    if code == 429:
                        consecutive += 1
                        delay = _backoff_delay(consecutive)
                        await asyncio.sleep(delay)
                        continue

                    if code == 403 or code == 400:
                        return None

                    if code == 200:
                        data = resp.json()
                        if isinstance(data, dict) and data.get("code") == "200":
                            cache.set(lat, lon, endpoint, data)
                            return data
                        if consecutive > 0:
                            consecutive = 0
                        continue

                    return None

                except httpx.TimeoutException:
                    consecutive += 1
                    await asyncio.sleep(_backoff_delay(consecutive))
                except Exception:
                    consecutive += 1
                    await asyncio.sleep(_backoff_delay(consecutive))

        return None

    @staticmethod
    def _compute_stats(daily, hourly):
        if not isinstance(daily, list) or not daily:
            return _empty_stats()

        try:
            tmax = max(_safe_int(d.get("tempMax", 0)) for d in daily)
            tmin = min(_safe_int(d.get("tempMin", 0)) for d in daily)
            total_precip = sum(_safe_float(d.get("precip", 0)) for d in daily)
            rain_days = sum(1 for d in daily if _safe_float(d.get("precip", 0)) > 0)
            max_wind = 0
            for d in daily:
                ws = d.get("windScaleDay", "0-0")
                if isinstance(ws, str) and "-" in ws:
                    max_wind = max(max_wind, _safe_int(ws.split("-")[-1]))
        except Exception:
            return _empty_stats()

        daily_summary = []
        for d in daily:
            daily_summary.append({
                "date": d.get("fxDate", ""),
                "tmax": _safe_int(d.get("tempMax", 0)),
                "tmin": _safe_int(d.get("tempMin", 0)),
                "textDay": d.get("textDay", ""),
                "textNight": d.get("textNight", ""),
                "windDay": d.get("windScaleDay", ""),
                "windNight": d.get("windScaleNight", ""),
                "precip": _safe_float(d.get("precip", 0)),
                "humidity": d.get("humidity", ""),
            })

        hours_above_40 = max_cont_40 = cur_40 = 0
        hours_above_38 = max_cont_38 = cur_38 = 0
        hours_above_37 = max_cont_37 = cur_37 = 0
        hours_above_35 = 0
        hours_below_0 = hours_below_5 = max_cont_below0 = cur_below0 = 0
        max_rain_hours = cur_rain = max_precip = 0
        flags = {k: False for k in WARNING_KEYS}

        if isinstance(hourly, list):
            for h in hourly:
                if not isinstance(h, dict):
                    continue
                t = _safe_float(h.get("temp", 0))
                p = _safe_float(h.get("precip", 0))
                txt = h.get("text", "")
                if t >= 40:
                    hours_above_40 += 1; cur_40 += 1
                    max_cont_40 = max(max_cont_40, cur_40)
                else:
                    cur_40 = 0
                if t >= 38:
                    hours_above_38 += 1; cur_38 += 1
                    max_cont_38 = max(max_cont_38, cur_38)
                else:
                    cur_38 = 0
                if t >= 37:
                    hours_above_37 += 1; cur_37 += 1
                    max_cont_37 = max(max_cont_37, cur_37)
                else:
                    cur_37 = 0
                if t >= 35:
                    hours_above_35 += 1
                if t <= 0:
                    hours_below_0 += 1; cur_below0 += 1
                    max_cont_below0 = max(max_cont_below0, cur_below0)
                else:
                    cur_below0 = 0
                if t <= 5:
                    hours_below_5 += 1
                if p > 0:
                    cur_rain += 1
                    max_rain_hours = max(max_rain_hours, cur_rain)
                    max_precip = max(max_precip, p)
                else:
                    cur_rain = 0
                for key, keywords in WEATHER_KEYWORDS.items():
                    k = f"has{key[0].upper()}{key[1:]}"
                    if not flags[k] and any(kw in txt for kw in keywords):
                        flags[k] = True

        return {
            "tmax": tmax, "tmin": tmin,
            "totalPrecip": total_precip, "rainDays": rain_days,
            "maxWind": max_wind,
            "hoursAbove40": hours_above_40, "maxCont40": max_cont_40,
            "hoursAbove38": hours_above_38, "maxCont38": max_cont_38,
            "hoursAbove37": hours_above_37, "maxCont37": max_cont_37,
            "hoursAbove35": hours_above_35,
            "hoursBelow0": hours_below_0, "hoursBelow5": hours_below_5,
            "maxContBelow0": max_cont_below0,
            "maxRainHours": max_rain_hours, "maxPrecip": max_precip,
            "dailySummary": daily_summary,
            **flags,
        }

    @staticmethod
    def _has_warning(stats):
        return (stats["tmax"] >= 38 or stats["tmin"] <= 0
                or stats["maxPrecip"] >= 16 or stats["maxWind"] >= 6
                or any(stats[k] for k in _SEVERE_KEYS))

    @staticmethod
    async def run(counties):
        sem = asyncio.Semaphore(MAX_CONCURRENT)
        headers = {"X-QW-API-KEY": QWEATHER_API_KEY}
        params_base = {"lang": "zh"}

        async with httpx.AsyncClient(headers=headers, limits=httpx.Limits(
            max_connections=MAX_CONCURRENT, max_keepalive_connections=20
        )) as client:
            daily_tasks = {}
            for c in counties:
                lat = c.get("lat", 0)
                lon = c.get("lon", 0)
                url = f"{QWEATHER_BASE_URL}/{FORECAST_DAYS}"
                p = {**params_base, "location": WeatherTool._loc(c)}
                daily_tasks[c["name"]] = WeatherTool._fetch(
                    client, sem, url, p, lat, lon, "7d", cache.DAILY_TTL
                )

            daily_results = dict(zip(
                daily_tasks.keys(),
                await asyncio.gather(*daily_tasks.values())
            ))

            hourly_tasks = {}
            date_ranges = {}
            for name, data in daily_results.items():
                if not isinstance(data, dict):
                    continue
                daily = data.get("daily")
                if not isinstance(daily, list) or not daily:
                    continue
                c = _find_county(counties, name)
                if not c:
                    continue
                lat = c.get("lat", 0)
                lon = c.get("lon", 0)
                url = f"{QWEATHER_BASE_URL}/{HOURLY_HOURS}h"
                p = {**params_base, "location": WeatherTool._loc(c)}
                date_ranges[name] = (
                    daily[0].get("fxDate", ""),
                    daily[-1].get("fxDate", "")
                )
                hourly_tasks[name] = WeatherTool._fetch(
                    client, sem, url, p, lat, lon, "168h", cache.HOURLY_TTL
                )

            hourly_results = {}
            if hourly_tasks:
                hourly_results = dict(zip(
                    hourly_tasks.keys(),
                    await asyncio.gather(*hourly_tasks.values())
                ))

        result = {"counties": [], "updateTime": None,
                  "total": len(counties), "warned": 0}
        for c in counties:
            name = c["name"]
            data = daily_results.get(name)
            if not isinstance(data, dict):
                continue
            if not result["updateTime"]:
                result["updateTime"] = data.get("updateTime")

            daily = data.get("daily")
            if not isinstance(daily, list) or not daily:
                continue

            hourly = None
            hr = hourly_results.get(name)
            if isinstance(hr, dict):
                start, end = date_ranges.get(name, ("", ""))
                hourly_list = hr.get("hourly", [])
                if isinstance(hourly_list, list) and start and end:
                    hourly = [h for h in hourly_list
                              if isinstance(h, dict) and start <= h.get("fxTime", "")[:10] <= end]

            stats = WeatherTool._compute_stats(daily, hourly)
            if WeatherTool._has_warning(stats):
                result["warned"] += 1
                result["counties"].append({
                    "name": name,
                    "county": c.get("county", ""),
                    **stats,
                })

        return result


def _empty_stats():
    return {
        "tmax": 0, "tmin": 0,
        "totalPrecip": 0, "rainDays": 0,
        "maxWind": 0,
        "hoursAbove40": 0, "maxCont40": 0,
        "hoursAbove38": 0, "maxCont38": 0,
        "hoursAbove37": 0, "maxCont37": 0,
        "hoursAbove35": 0,
        "hoursBelow0": 0, "hoursBelow5": 0,
        "maxContBelow0": 0,
        "maxRainHours": 0, "maxPrecip": 0,
        "dailySummary": [],
        "hasThunder": False, "hasSnow": False, "hasFreezing": False,
        "hasHail": False, "hasFog": False, "hasHaze": False, "hasSand": False,
    }


_COUNTY_MAP = {}

def _find_county(counties, name):
    for c in counties:
        if c.get("name") == name:
            return c
    return None
