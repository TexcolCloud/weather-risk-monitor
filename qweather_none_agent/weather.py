
import asyncio
import logging
import random
import re
from collections import deque
from datetime import datetime, timedelta

import httpx
from .config import (
    QWEATHER_API_KEY,
    QWEATHER_BASE_URL,
    QWEATHER_WARNING_URL,
    FORECAST_DAYS,
    HOURLY_HOURS,
)
from . import cache
from .standards import is_warning


logger = logging.getLogger(__name__)

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

WARNING_COLOR_LEVELS = {
    "white": 0,
    "blue": 1,
    "green": 1,
    "yellow": 2,
    "orange": 3,
    "red": 4,
    "白色": 0,
    "蓝色": 1,
    "绿色": 1,
    "黄色": 2,
    "橙色": 3,
    "红色": 4,
}

WARNING_KEYS = [
    "hasThunder", "hasSnow", "hasFreezing", "hasHail",
    "hasFog", "hasHaze", "hasSand",
]

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


def _parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _wind_scale_max(val):
    numbers = re.findall(r"\d+", str(val))
    if not numbers:
        return 0
    return max(_safe_int(n) for n in numbers)


def _prepare_hourly(hourly):
    if not isinstance(hourly, list) or not hourly:
        return [], False

    by_time = {}
    complete = True
    for item in hourly:
        if not isinstance(item, dict):
            complete = False
            continue
        fx_time = _parse_time(item.get("fxTime"))
        if fx_time is None:
            complete = False
            continue
        if fx_time in by_time:
            complete = False
        by_time[fx_time] = item

    records = sorted(by_time.items(), key=lambda item: item[0])
    if not records:
        return [], False
    for index in range(1, len(records)):
        if records[index][0] - records[index - 1][0] != timedelta(hours=1):
            complete = False
    return records, complete


def _max_rolling_sum(records, window):
    if not records:
        return 0.0
    best = current = 0.0
    queue = deque()
    for fx_time, value in records:
        queue.append((fx_time, value))
        current += value
        cutoff = fx_time - timedelta(hours=window)
        while queue and queue[0][0] <= cutoff:
            current -= queue.popleft()[1]
        best = max(best, current)
    return round(best, 1)


def _warning_color(raw):
    if isinstance(raw, dict):
        raw = raw.get("code") or raw.get("name") or raw.get("color")
    color = str(raw or "").strip().lower()
    if color.isdigit():
        numeric = int(color)
        return {1: "蓝色", 2: "黄色", 3: "橙色", 4: "红色"}.get(numeric, "")
    mapping = {
        "blue": "蓝色",
        "green": "蓝色",
        "yellow": "黄色",
        "orange": "橙色",
        "red": "红色",
        "白色": "白色",
        "蓝色": "蓝色",
        "绿色": "蓝色",
        "黄色": "黄色",
        "橙色": "橙色",
        "红色": "红色",
    }
    return mapping.get(color, str(raw or "").strip())


def _warning_level(color):
    return WARNING_COLOR_LEVELS.get(str(color or "").strip().lower(), 0)


def _normalize_warnings(data):
    if not isinstance(data, dict):
        return []
    raw_warnings = data.get("warning")
    if raw_warnings is None:
        raw_warnings = data.get("alerts")
    if not isinstance(raw_warnings, list):
        return []

    warnings = []
    for item in raw_warnings:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").lower()
        if status in {"cancel", "cancelled", "解除", "已解除"}:
            continue
        color = _warning_color(
            item.get("severityColor")
            or item.get("color")
            or item.get("severity")
            or item.get("level")
        )
        title = item.get("title") or item.get("headline") or ""
        type_name = item.get("typeName") or item.get("eventType") or item.get("type") or ""
        warnings.append({
            "id": item.get("id") or item.get("identifier") or "",
            "title": title,
            "typeName": type_name,
            "level": item.get("level") or item.get("severity") or "",
            "color": color,
            "levelScore": _warning_level(color),
            "text": item.get("text") or item.get("description") or item.get("instruction") or "",
            "sender": item.get("sender") or item.get("senderName") or "",
            "pubTime": item.get("pubTime") or item.get("sent") or item.get("effective") or "",
        })
    warnings.sort(key=lambda w: w["levelScore"], reverse=True)
    return warnings


class WeatherTool:

    @staticmethod
    def _loc(c):
        lat = _safe_float(c.get("lat"), 0.0)
        lon = _safe_float(c.get("lon"), 0.0)
        return f"{lon:.2f},{lat:.2f}"

    @staticmethod
    async def _fetch(client, sem, url, params, lat, lon, endpoint, ttl):
        cached = cache.get(lat, lon, endpoint, ttl)
        if cached is not None:
            return cached

        consecutive = 0
        for _ in range(MAX_RETRIES):
            delay = None
            try:
                async with sem:
                    resp = await client.get(url, params=params, timeout=10)
                code = resp.status_code

                if code == 429:
                    consecutive += 1
                    delay = _backoff_delay(consecutive)

                elif code == 403 or code == 400:
                    logger.warning("天气接口拒绝请求: endpoint=%s status=%s", endpoint, code)
                    return None

                elif code == 200:
                    data = resp.json()
                    if isinstance(data, dict) and data.get("code") == "200":
                        cache.set(lat, lon, endpoint, data)
                        return data
                    consecutive += 1
                    delay = _backoff_delay(consecutive)

                elif code >= 500:
                    consecutive += 1
                    delay = _backoff_delay(consecutive)

                else:
                    logger.warning("天气接口返回异常状态: endpoint=%s status=%s", endpoint, code)
                    return None

            except httpx.TimeoutException:
                consecutive += 1
                delay = _backoff_delay(consecutive)
            except Exception:
                logger.exception("天气接口请求异常: endpoint=%s", endpoint)
                consecutive += 1
                delay = _backoff_delay(consecutive)

            if delay is not None:
                await asyncio.sleep(delay)

        return None

    @staticmethod
    def _compute_stats(daily, hourly):
        if not isinstance(daily, list) or not daily:
            return _empty_stats()

        daily_records = [item for item in daily if isinstance(item, dict)]
        if not daily_records:
            return _empty_stats()

        tmax_values = [
            value for value in (_safe_int(d.get("tempMax"), None) for d in daily_records)
            if value is not None
        ]
        tmin_values = [
            value for value in (_safe_int(d.get("tempMin"), None) for d in daily_records)
            if value is not None
        ]
        precip_values = [max(_safe_float(d.get("precip"), 0.0), 0.0) for d in daily_records]
        tmax = max(tmax_values) if tmax_values else None
        tmin = min(tmin_values) if tmin_values else None
        total_precip = sum(precip_values)
        rain_days = sum(1 for value in precip_values if value > 0)
        max_daily_precip = max(precip_values, default=0.0)
        max_cont_daily_35 = cur_daily_35 = 0
        max_wind = 0
        flags = {key: False for key in WARNING_KEYS}

        for d in daily_records:
            daily_tmax = _safe_int(d.get("tempMax"), None)
            if daily_tmax is not None and daily_tmax > 35:
                cur_daily_35 += 1
                max_cont_daily_35 = max(max_cont_daily_35, cur_daily_35)
            else:
                cur_daily_35 = 0
            max_wind = max(
                max_wind,
                _wind_scale_max(d.get("windScaleDay", "")),
                _wind_scale_max(d.get("windScaleNight", "")),
            )
            full_text = f"{d.get('textDay', '')}{d.get('textNight', '')}"
            for key, keywords in WEATHER_KEYWORDS.items():
                flag = f"has{key[0].upper()}{key[1:]}"
                if not flags[flag] and any(keyword in full_text for keyword in keywords):
                    flags[flag] = True

        daily_summary = []
        for d in daily_records:
            daily_summary.append({
                "date": d.get("fxDate", ""),
                "tmax": _safe_int(d.get("tempMax"), None),
                "tmin": _safe_int(d.get("tempMin"), None),
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
        hourly_records, hourly_complete = _prepare_hourly(hourly)
        expected_dates = {d.get("fxDate") for d in daily_records if d.get("fxDate")}
        hourly_dates = {fx_time.date().isoformat() for fx_time, _ in hourly_records}
        if expected_dates and not expected_dates.issubset(hourly_dates):
            hourly_complete = False
        hourly_precip = []
        previous_time = None

        for fx_time, h in hourly_records:
            contiguous = previous_time is not None and fx_time - previous_time == timedelta(hours=1)
            if not contiguous:
                cur_40 = cur_38 = cur_37 = cur_below0 = cur_rain = 0
            previous_time = fx_time

            t = _safe_float(h.get("temp"), None)
            p = _safe_float(h.get("precip"), None)
            if t is None or p is None:
                hourly_complete = False
            precip = max(p or 0.0, 0.0)
            hourly_precip.append((fx_time, precip))
            txt = h.get("text", "")
            if t is not None and t > 40:
                hours_above_40 += 1
                cur_40 += 1
                max_cont_40 = max(max_cont_40, cur_40)
            else:
                cur_40 = 0
            if t is not None and t > 38:
                hours_above_38 += 1
                cur_38 += 1
                max_cont_38 = max(max_cont_38, cur_38)
            else:
                cur_38 = 0
            if t is not None and t > 37:
                hours_above_37 += 1
                cur_37 += 1
                max_cont_37 = max(max_cont_37, cur_37)
            else:
                cur_37 = 0
            if t is not None and t > 35:
                hours_above_35 += 1
            if t is not None and t <= 0:
                hours_below_0 += 1
                cur_below0 += 1
                max_cont_below0 = max(max_cont_below0, cur_below0)
            else:
                cur_below0 = 0
            if t is not None and t <= 5:
                hours_below_5 += 1
            if p is not None and p > 0:
                cur_rain += 1
                max_rain_hours = max(max_rain_hours, cur_rain)
                max_precip = max(max_precip, p)
            else:
                cur_rain = 0
            for key, keywords in WEATHER_KEYWORDS.items():
                flag = f"has{key[0].upper()}{key[1:]}"
                if not flags[flag] and any(keyword in txt for keyword in keywords):
                    flags[flag] = True

        max_precip_3h = _max_rolling_sum(hourly_precip, 3)
        max_precip_6h = _max_rolling_sum(hourly_precip, 6)
        max_precip_12h = _max_rolling_sum(hourly_precip, 12)
        max_precip_24h = _max_rolling_sum(hourly_precip, 24)
        max_precip_24h = max(max_precip_24h, round(max_daily_precip, 1))

        return {
            "tmax": tmax, "tmin": tmin,
            "totalPrecip": total_precip, "rainDays": rain_days,
            "maxDailyPrecip": max_daily_precip,
            "maxWind": max_wind,
            "hoursAbove40": hours_above_40, "maxCont40": max_cont_40,
            "hoursAbove38": hours_above_38, "maxCont38": max_cont_38,
            "hoursAbove37": hours_above_37, "maxCont37": max_cont_37,
            "hoursAbove35": hours_above_35, "maxContDaily35": max_cont_daily_35,
            "hoursBelow0": hours_below_0, "hoursBelow5": hours_below_5,
            "maxContBelow0": max_cont_below0,
            "maxRainHours": max_rain_hours, "maxPrecip": max_precip,
            "maxPrecip3h": max_precip_3h, "maxPrecip6h": max_precip_6h,
            "maxPrecip12h": max_precip_12h, "maxPrecip24h": max_precip_24h,
            "dailySummary": daily_summary,
            "dailyDataComplete": (
                len(daily_records) == len(daily)
                and len(tmax_values) == len(daily_records)
                and len(tmin_values) == len(daily_records)
            ),
            "hourlyDataComplete": hourly_complete,
            **flags,
        }

    @staticmethod
    def _has_warning(stats):
        return is_warning(stats)

    @staticmethod
    async def run(counties):
        names = [c.get("name") for c in counties]
        if any(not name for name in names) or len(names) != len(set(names)):
            raise ValueError("机房名称不能为空且必须唯一")

        sem = asyncio.Semaphore(MAX_CONCURRENT)
        headers = {"X-QW-API-KEY": QWEATHER_API_KEY}
        params_base = {"lang": "zh"}
        counties_by_name = {c["name"]: c for c in counties}
        warning_key_by_name = {}

        async with httpx.AsyncClient(headers=headers, limits=httpx.Limits(
            max_connections=MAX_CONCURRENT, max_keepalive_connections=20
        )) as client:
            daily_tasks = {}
            warning_tasks = {}
            for c in counties:
                lat = c.get("lat", 0)
                lon = c.get("lon", 0)
                url = f"{QWEATHER_BASE_URL}/{FORECAST_DAYS}"
                p = {**params_base, "location": WeatherTool._loc(c)}
                daily_tasks[c["name"]] = WeatherTool._fetch(
                    client, sem, url, p, lat, lon, "7d", cache.DAILY_TTL
                )
                warning_key = c.get("county") or c["name"]
                warning_key_by_name[c["name"]] = warning_key
                if warning_key not in warning_tasks:
                    warning_tasks[warning_key] = WeatherTool._fetch(
                        client, sem, QWEATHER_WARNING_URL, p, lat, lon,
                        "warning", cache.WARNING_TTL
                    )

            daily_results = dict(zip(
                daily_tasks.keys(),
                await asyncio.gather(*daily_tasks.values())
            ))
            warning_results = dict(zip(
                warning_tasks.keys(),
                await asyncio.gather(*warning_tasks.values())
            ))

            hourly_tasks = {}
            date_ranges = {}
            for name, data in daily_results.items():
                if not isinstance(data, dict):
                    continue
                daily = [item for item in data.get("daily", []) if isinstance(item, dict)]
                if not daily:
                    continue
                c = counties_by_name[name]
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

        result = {
            "counties": [],
            "updateTime": None,
            "total": len(counties),
            "warned": 0,
            "failed": 0,
            "partialFailed": 0,
            "warningFailed": 0,
            "dailyIncomplete": 0,
            "failedRooms": [],
            "partialFailedRooms": [],
            "warningFailedRooms": [],
            "dailyIncompleteRooms": [],
        }
        for c in counties:
            name = c["name"]
            data = daily_results.get(name)
            daily = data.get("daily") if isinstance(data, dict) else None
            daily_ok = isinstance(daily, list) and any(isinstance(item, dict) for item in daily)
            if not daily_ok:
                result["failed"] += 1
                result["failedRooms"].append(name)

            hourly = None
            if daily_ok:
                if not result["updateTime"]:
                    result["updateTime"] = data.get("updateTime")
                hr = hourly_results.get(name)
                if isinstance(hr, dict):
                    start, end = date_ranges.get(name, ("", ""))
                    hourly_list = hr.get("hourly", [])
                    if isinstance(hourly_list, list) and start and end:
                        hourly = [
                            item for item in hourly_list
                            if isinstance(item, dict)
                            and start <= str(item.get("fxTime", ""))[:10] <= end
                        ]
                stats = WeatherTool._compute_stats(daily, hourly)
                if not stats["dailyDataComplete"]:
                    result["dailyIncomplete"] += 1
                    result["dailyIncompleteRooms"].append(name)
                if not stats["hourlyDataComplete"]:
                    result["partialFailed"] += 1
                    result["partialFailedRooms"].append(name)
            else:
                stats = _empty_stats()

            warning_key = warning_key_by_name[name]
            warning_data = warning_results.get(warning_key)
            if not isinstance(warning_data, dict):
                result["warningFailed"] += 1
                result["warningFailedRooms"].append(name)
            elif not result["updateTime"]:
                result["updateTime"] = warning_data.get("updateTime")

            official_warnings = _normalize_warnings(warning_data)
            if official_warnings:
                stats["officialWarnings"] = official_warnings
                stats["officialWarningLevel"] = official_warnings[0]["color"]
                stats["officialWarningTitle"] = official_warnings[0]["title"]
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
        "tmax": None, "tmin": None,
        "totalPrecip": 0, "rainDays": 0, "maxDailyPrecip": 0,
        "maxWind": 0,
        "hoursAbove40": 0, "maxCont40": 0,
        "hoursAbove38": 0, "maxCont38": 0,
        "hoursAbove37": 0, "maxCont37": 0,
        "hoursAbove35": 0, "maxContDaily35": 0,
        "hoursBelow0": 0, "hoursBelow5": 0,
        "maxContBelow0": 0,
        "maxRainHours": 0, "maxPrecip": 0,
        "maxPrecip3h": 0, "maxPrecip6h": 0,
        "maxPrecip12h": 0, "maxPrecip24h": 0,
        "officialWarnings": [],
        "officialWarningLevel": "",
        "officialWarningTitle": "",
        "dailySummary": [],
        "dailyDataComplete": False,
        "hourlyDataComplete": False,
        "hasThunder": False, "hasSnow": False, "hasFreezing": False,
        "hasHail": False, "hasFog": False, "hasHaze": False, "hasSand": False,
    }
