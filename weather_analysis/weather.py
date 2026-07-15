"""Orchestration for collecting and combining room weather data."""

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import cache
from .config import (
    FORECAST_DAYS,
    HOURLY_HOURS,
    QWEATHER_API_KEY,
    QWEATHER_BASE_URL,
    QWEATHER_WARNING_URL,
)
from .models import HourlyRiskResult, Room, WeatherFetchResult
from .qweather_client import QWeatherClient, normalize_warnings
from .warning_rules import (
    forecast_risk_score,
    is_forecast_significant,
    is_forecast_warning,
)
from .weather_stats import compute_weather_stats, empty_weather_stats, hourly_window_stats


LOCAL_TIMEZONE = ZoneInfo("Asia/Shanghai")


class WeatherService:
    @staticmethod
    def _compute_stats(daily, hourly):
        """Compatibility wrapper for callers migrating to weather_stats."""
        return compute_weather_stats(daily, hourly)

    @staticmethod
    def _validate_rooms(rooms: list[Room]) -> None:
        names = [room.get("name") for room in rooms]
        if any(not name for name in names) or len(names) != len(set(names)):
            raise ValueError("机房名称不能为空且必须唯一")

    @staticmethod
    def _attach_warnings(stats: dict, warning_data) -> list[dict]:
        official_warnings = normalize_warnings(warning_data)
        if official_warnings:
            stats["officialWarnings"] = official_warnings
            stats["officialWarningLevel"] = official_warnings[0]["color"]
            stats["officialWarningTitle"] = official_warnings[0]["title"]
        return official_warnings

    @staticmethod
    def _risk_room(room: Room, stats: dict, records: list[dict], start: datetime, end: datetime) -> dict:
        def temp_value(record):
            try:
                return float(record.get("temp"))
            except (AttributeError, TypeError, ValueError):
                return float("-inf")

        peak = max(records, key=temp_value, default={})
        weather_texts = list(
            dict.fromkeys(str(record.get("text", "")).strip() for record in records if record.get("text"))
        )
        return {
            "name": room["name"],
            "county": room.get("county", ""),
            "timeRange": f"{start.isoformat()}/{end.isoformat()}",
            "riskTime": peak.get("fxTime", start.isoformat()),
            "weatherText": "、".join(weather_texts),
            "temperature": stats.get("tmax"),
            "windScale": peak.get("windScale", ""),
            "precipitation": stats.get("maxPrecip", 0),
            "stats": stats,
        }

    @staticmethod
    def _sort_risks(risks: list[dict]) -> list[dict]:
        risks.sort(key=lambda risk: (risk.get("county", ""), risk.get("name", "")))
        risks.sort(key=lambda risk: forecast_risk_score(risk.get("stats", {})), reverse=True)
        return risks

    @staticmethod
    async def run(rooms: list[Room]) -> WeatherFetchResult:
        WeatherService._validate_rooms(rooms)

        params_base = {"lang": "zh"}
        rooms_by_name = {room["name"]: room for room in rooms}
        warning_key_by_name = {}

        async with QWeatherClient(QWEATHER_API_KEY) as client:
            daily_tasks = {}
            warning_tasks = {}
            for room in rooms:
                name = room["name"]
                lat = room.get("lat", 0)
                lon = room.get("lon", 0)
                params = {**params_base, "location": client.location(room)}
                daily_tasks[name] = client.fetch(
                    f"{QWEATHER_BASE_URL}/{FORECAST_DAYS}",
                    params,
                    lat,
                    lon,
                    "7d",
                    cache.DAILY_TTL,
                )

                warning_key = room.get("county") or name
                warning_key_by_name[name] = warning_key
                if warning_key not in warning_tasks:
                    warning_tasks[warning_key] = client.fetch(
                        QWEATHER_WARNING_URL,
                        params,
                        lat,
                        lon,
                        "warning",
                        cache.WARNING_TTL,
                    )

            daily_results = dict(
                zip(
                    daily_tasks,
                    await asyncio.gather(*daily_tasks.values()),
                )
            )
            warning_results = dict(
                zip(
                    warning_tasks,
                    await asyncio.gather(*warning_tasks.values()),
                )
            )

            hourly_tasks = {}
            date_ranges = {}
            for name, data in daily_results.items():
                if not isinstance(data, dict):
                    continue
                daily = [item for item in data.get("daily", []) if isinstance(item, dict)]
                if not daily:
                    continue
                room = rooms_by_name[name]
                lat = room.get("lat", 0)
                lon = room.get("lon", 0)
                params = {**params_base, "location": client.location(room)}
                date_ranges[name] = (
                    daily[0].get("fxDate", ""),
                    daily[-1].get("fxDate", ""),
                )
                hourly_tasks[name] = client.fetch(
                    f"{QWEATHER_BASE_URL}/{HOURLY_HOURS}h",
                    params,
                    lat,
                    lon,
                    "168h",
                    cache.HOURLY_TTL,
                )

            hourly_results = {}
            if hourly_tasks:
                hourly_results = dict(
                    zip(
                        hourly_tasks,
                        await asyncio.gather(*hourly_tasks.values()),
                    )
                )

        result: WeatherFetchResult = {
            "counties": [],
            "updateTime": None,
            "total": len(rooms),
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

        for room in rooms:
            name = room["name"]
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
                hourly_response = hourly_results.get(name)
                if isinstance(hourly_response, dict):
                    start, end = date_ranges.get(name, ("", ""))
                    hourly_list = hourly_response.get("hourly", [])
                    if isinstance(hourly_list, list) and start and end:
                        hourly = [
                            item
                            for item in hourly_list
                            if isinstance(item, dict)
                            and start <= str(item.get("fxTime", ""))[:10] <= end
                        ]
                stats = compute_weather_stats(daily, hourly)
                if not stats["dailyDataComplete"]:
                    result["dailyIncomplete"] += 1
                    result["dailyIncompleteRooms"].append(name)
                if not stats["hourlyDataComplete"]:
                    result["partialFailed"] += 1
                    result["partialFailedRooms"].append(name)
            else:
                stats = empty_weather_stats()

            warning_key = warning_key_by_name[name]
            warning_data = warning_results.get(warning_key)
            if not isinstance(warning_data, dict):
                result["warningFailed"] += 1
                result["warningFailedRooms"].append(name)
            elif not result["updateTime"]:
                result["updateTime"] = warning_data.get("updateTime")

            WeatherService._attach_warnings(stats, warning_data)
            if is_forecast_warning(stats):
                result["warned"] += 1
                result["counties"].append(
                    {
                        "name": name,
                        "county": room.get("county", ""),
                        **stats,
                    }
                )

        return result

    @staticmethod
    async def run_hourly_risk(rooms: list[Room], target_start: datetime) -> HourlyRiskResult:
        """Collect forecast data for one exact hour plus its three-hour outlook."""
        WeatherService._validate_rooms(rooms)
        if target_start.tzinfo is None:
            target_start = target_start.replace(tzinfo=LOCAL_TIMEZONE)
        else:
            target_start = target_start.astimezone(LOCAL_TIMEZONE)
        target_start = target_start.replace(minute=0, second=0, microsecond=0)
        immediate_end = target_start + timedelta(hours=1)
        outlook_end = target_start + timedelta(hours=3)

        params_base = {"lang": "zh"}
        warning_key_by_name = {}
        async with QWeatherClient(QWEATHER_API_KEY) as client:
            hourly_tasks = {}
            warning_tasks = {}
            for room in rooms:
                name = room["name"]
                lat = room.get("lat", 0)
                lon = room.get("lon", 0)
                params = {**params_base, "location": client.location(room)}
                hourly_tasks[name] = client.fetch(
                    f"{QWEATHER_BASE_URL}/{HOURLY_HOURS}h",
                    params,
                    lat,
                    lon,
                    "168h",
                    cache.HOURLY_TTL,
                )

                warning_key = room.get("county") or name
                warning_key_by_name[name] = warning_key
                if warning_key not in warning_tasks:
                    warning_tasks[warning_key] = client.fetch(
                        QWEATHER_WARNING_URL,
                        params,
                        lat,
                        lon,
                        "warning",
                        cache.WARNING_TTL,
                    )

            hourly_results = dict(zip(hourly_tasks, await asyncio.gather(*hourly_tasks.values())))
            warning_results = dict(zip(warning_tasks, await asyncio.gather(*warning_tasks.values())))

        result: HourlyRiskResult = {
            "targetStart": target_start.isoformat(),
            "immediateEnd": immediate_end.isoformat(),
            "outlookEnd": outlook_end.isoformat(),
            "updateTime": None,
            "total": len(rooms),
            "failed": 0,
            "partialFailed": 0,
            "warningFailed": 0,
            "immediateRisks": [],
            "outlookRisks": [],
            "failedRooms": [],
            "partialFailedRooms": [],
            "warningFailedRooms": [],
        }

        for room in rooms:
            name = room["name"]
            hourly_data = hourly_results.get(name)
            hourly = hourly_data.get("hourly") if isinstance(hourly_data, dict) else None
            immediate_stats, immediate_records = hourly_window_stats(hourly, target_start, 1)
            outlook_stats, outlook_records = hourly_window_stats(hourly, target_start, 3)

            if isinstance(hourly_data, dict) and not result["updateTime"]:
                result["updateTime"] = hourly_data.get("updateTime")
            if not immediate_stats["hourlyDataComplete"]:
                result["failed"] += 1
                result["failedRooms"].append(name)
            elif not outlook_stats["hourlyDataComplete"]:
                result["partialFailed"] += 1
                result["partialFailedRooms"].append(name)

            warning_data = warning_results.get(warning_key_by_name[name])
            if not isinstance(warning_data, dict):
                result["warningFailed"] += 1
                result["warningFailedRooms"].append(name)
            elif not result["updateTime"]:
                result["updateTime"] = warning_data.get("updateTime")

            WeatherService._attach_warnings(immediate_stats, warning_data)
            WeatherService._attach_warnings(outlook_stats, warning_data)
            if is_forecast_significant(immediate_stats):
                result["immediateRisks"].append(
                    WeatherService._risk_room(room, immediate_stats, immediate_records, target_start, immediate_end)
                )
            if is_forecast_significant(outlook_stats):
                result["outlookRisks"].append(
                    WeatherService._risk_room(room, outlook_stats, outlook_records, target_start, outlook_end)
                )

        WeatherService._sort_risks(result["immediateRisks"])
        WeatherService._sort_risks(result["outlookRisks"])
        return result


# Backward-compatible name for existing integrations.
WeatherTool = WeatherService
