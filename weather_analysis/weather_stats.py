"""Pure calculations for daily and hourly weather forecasts."""

import re
from collections import deque
from datetime import datetime, timedelta

from .models import WeatherStats


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
    "hasThunder",
    "hasSnow",
    "hasFreezing",
    "hasHail",
    "hasFog",
    "hasHaze",
    "hasSand",
]


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _wind_scale_max(value):
    numbers = re.findall(r"\d+", str(value))
    return max((_safe_int(number) for number in numbers), default=0)


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


def hourly_window_stats(hourly, start: datetime, hours: int) -> tuple[WeatherStats, list[dict]]:
    """Calculate risk inputs for an exact, contiguous hourly forecast window."""
    if hours < 1:
        raise ValueError("hours must be positive")

    expected = [start + timedelta(hours=index) for index in range(hours)]
    records, _ = _prepare_hourly(hourly)
    by_time = dict(records)
    window = [by_time[time] for time in expected if time in by_time]
    complete = len(window) == hours

    stats = empty_weather_stats()
    stats["hourlyDataComplete"] = complete
    if not window:
        return stats, []

    temperatures = []
    precipitation = []
    max_wind = 0
    flags = {key: False for key in WARNING_KEYS}
    for hour in window:
        temperature = _safe_float(hour.get("temp"), None)
        precip = _safe_float(hour.get("precip"), None)
        if temperature is None or precip is None:
            stats["hourlyDataComplete"] = False
        if temperature is not None:
            temperatures.append(temperature)
        if precip is not None:
            precipitation.append(max(precip, 0.0))
        max_wind = max(max_wind, _wind_scale_max(hour.get("windScale", "")))
        _set_weather_flags(flags, hour.get("text", ""))

    stats.update(
        {
            "tmax": max(temperatures) if temperatures else None,
            "tmin": min(temperatures) if temperatures else None,
            "maxWind": max_wind,
            "maxPrecip": max(precipitation, default=0.0),
            # Only a complete three-hour window can support a rainstorm rule.
            "maxPrecip3h": round(sum(precipitation), 1)
            if hours == 3 and stats["hourlyDataComplete"]
            else 0.0,
            **flags,
        }
    )
    return stats, window


def _set_weather_flags(flags, text):
    for key, keywords in WEATHER_KEYWORDS.items():
        flag = f"has{key[0].upper()}{key[1:]}"
        if not flags[flag] and any(keyword in text for keyword in keywords):
            flags[flag] = True


def compute_weather_stats(daily, hourly) -> WeatherStats:
    if not isinstance(daily, list) or not daily:
        return empty_weather_stats()

    daily_records = [item for item in daily if isinstance(item, dict)]
    if not daily_records:
        return empty_weather_stats()

    tmax_values = [
        value
        for value in (_safe_int(day.get("tempMax"), None) for day in daily_records)
        if value is not None
    ]
    tmin_values = [
        value
        for value in (_safe_int(day.get("tempMin"), None) for day in daily_records)
        if value is not None
    ]
    precip_values = [max(_safe_float(day.get("precip"), 0.0), 0.0) for day in daily_records]
    tmax = max(tmax_values) if tmax_values else None
    tmin = min(tmin_values) if tmin_values else None
    total_precip = sum(precip_values)
    rain_days = sum(1 for value in precip_values if value > 0)
    max_daily_precip = max(precip_values, default=0.0)
    max_cont_daily_35 = cur_daily_35 = 0
    max_wind = 0
    flags = {key: False for key in WARNING_KEYS}

    for day in daily_records:
        daily_tmax = _safe_int(day.get("tempMax"), None)
        if daily_tmax is not None and daily_tmax >= 35:
            cur_daily_35 += 1
            max_cont_daily_35 = max(max_cont_daily_35, cur_daily_35)
        else:
            cur_daily_35 = 0
        max_wind = max(
            max_wind,
            _wind_scale_max(day.get("windScaleDay", "")),
            _wind_scale_max(day.get("windScaleNight", "")),
        )
        _set_weather_flags(flags, f"{day.get('textDay', '')}{day.get('textNight', '')}")

    daily_summary = [
        {
            "date": day.get("fxDate", ""),
            "tmax": _safe_int(day.get("tempMax"), None),
            "tmin": _safe_int(day.get("tempMin"), None),
            "textDay": day.get("textDay", ""),
            "textNight": day.get("textNight", ""),
            "windDay": day.get("windScaleDay", ""),
            "windNight": day.get("windScaleNight", ""),
            "precip": _safe_float(day.get("precip", 0)),
            "humidity": day.get("humidity", ""),
        }
        for day in daily_records
    ]

    hours_above_40 = max_cont_40 = cur_40 = 0
    hours_above_38 = max_cont_38 = cur_38 = 0
    hours_above_37 = max_cont_37 = cur_37 = 0
    hours_above_35 = 0
    hours_below_0 = hours_below_5 = max_cont_below0 = cur_below0 = 0
    max_rain_hours = cur_rain = max_precip = 0
    hourly_records, hourly_complete = _prepare_hourly(hourly)
    expected_dates = {day.get("fxDate") for day in daily_records if day.get("fxDate")}
    hourly_dates = {fx_time.date().isoformat() for fx_time, _ in hourly_records}
    if expected_dates and not expected_dates.issubset(hourly_dates):
        hourly_complete = False
    hourly_precip = []
    previous_time = None

    for fx_time, hour in hourly_records:
        contiguous = previous_time is not None and fx_time - previous_time == timedelta(hours=1)
        if not contiguous:
            cur_40 = cur_38 = cur_37 = cur_below0 = cur_rain = 0
        previous_time = fx_time

        temperature = _safe_float(hour.get("temp"), None)
        precipitation = _safe_float(hour.get("precip"), None)
        if temperature is None or precipitation is None:
            hourly_complete = False
        precip = max(precipitation or 0.0, 0.0)
        hourly_precip.append((fx_time, precip))
        _set_weather_flags(flags, hour.get("text", ""))

        if temperature is not None and temperature >= 40:
            hours_above_40 += 1
            cur_40 += 1
            max_cont_40 = max(max_cont_40, cur_40)
        else:
            cur_40 = 0
        if temperature is not None and temperature >= 38:
            hours_above_38 += 1
            cur_38 += 1
            max_cont_38 = max(max_cont_38, cur_38)
        else:
            cur_38 = 0
        if temperature is not None and temperature >= 37:
            hours_above_37 += 1
            cur_37 += 1
            max_cont_37 = max(max_cont_37, cur_37)
        else:
            cur_37 = 0
        if temperature is not None and temperature >= 35:
            hours_above_35 += 1
        if temperature is not None and temperature <= 0:
            hours_below_0 += 1
            cur_below0 += 1
            max_cont_below0 = max(max_cont_below0, cur_below0)
        else:
            cur_below0 = 0
        if temperature is not None and temperature <= 5:
            hours_below_5 += 1
        if precipitation is not None and precipitation > 0:
            cur_rain += 1
            max_rain_hours = max(max_rain_hours, cur_rain)
            max_precip = max(max_precip, precipitation)
        else:
            cur_rain = 0

    max_precip_3h = _max_rolling_sum(hourly_precip, 3)
    max_precip_6h = _max_rolling_sum(hourly_precip, 6)
    max_precip_12h = _max_rolling_sum(hourly_precip, 12)
    max_precip_24h = max(
        _max_rolling_sum(hourly_precip, 24),
        round(max_daily_precip, 1),
    )

    return {
        "tmax": tmax,
        "tmin": tmin,
        "totalPrecip": total_precip,
        "rainDays": rain_days,
        "maxDailyPrecip": max_daily_precip,
        "maxWind": max_wind,
        "hoursAbove40": hours_above_40,
        "maxCont40": max_cont_40,
        "hoursAbove38": hours_above_38,
        "maxCont38": max_cont_38,
        "hoursAbove37": hours_above_37,
        "maxCont37": max_cont_37,
        "hoursAbove35": hours_above_35,
        "maxContDaily35": max_cont_daily_35,
        "hoursBelow0": hours_below_0,
        "hoursBelow5": hours_below_5,
        "maxContBelow0": max_cont_below0,
        "maxRainHours": max_rain_hours,
        "maxPrecip": max_precip,
        "maxPrecip3h": max_precip_3h,
        "maxPrecip6h": max_precip_6h,
        "maxPrecip12h": max_precip_12h,
        "maxPrecip24h": max_precip_24h,
        "dailySummary": daily_summary,
        "dailyDataComplete": (
            len(daily_records) == len(daily)
            and len(tmax_values) == len(daily_records)
            and len(tmin_values) == len(daily_records)
        ),
        "hourlyDataComplete": hourly_complete,
        **flags,
    }


def empty_weather_stats() -> WeatherStats:
    return {
        "tmax": None,
        "tmin": None,
        "totalPrecip": 0,
        "rainDays": 0,
        "maxDailyPrecip": 0,
        "maxWind": 0,
        "hoursAbove40": 0,
        "maxCont40": 0,
        "hoursAbove38": 0,
        "maxCont38": 0,
        "hoursAbove37": 0,
        "maxCont37": 0,
        "hoursAbove35": 0,
        "maxContDaily35": 0,
        "hoursBelow0": 0,
        "hoursBelow5": 0,
        "maxContBelow0": 0,
        "maxRainHours": 0,
        "maxPrecip": 0,
        "maxPrecip3h": 0,
        "maxPrecip6h": 0,
        "maxPrecip12h": 0,
        "maxPrecip24h": 0,
        "officialWarnings": [],
        "officialWarningLevel": "",
        "officialWarningTitle": "",
        "dailySummary": [],
        "dailyDataComplete": False,
        "hourlyDataComplete": False,
        "hasThunder": False,
        "hasSnow": False,
        "hasFreezing": False,
        "hasHail": False,
        "hasFog": False,
        "hasHaze": False,
        "hasSand": False,
    }
