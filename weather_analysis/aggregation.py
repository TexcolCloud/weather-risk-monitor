"""Aggregation helpers for converting room risks into county risks."""

from collections import defaultdict

from .models import CountyRisk, OfficialWarning, Room, WeatherStats
from .warning_rules import forecast_risk_score


def to_number(value, default=0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return int(number) if number.is_integer() else number


def room_with_extreme(rooms, field, highest=True):
    candidates = [room for room in rooms if to_number(room.get(field), None) is not None]
    if not candidates:
        return None
    selector = max if highest else min
    return selector(candidates, key=lambda room: to_number(room.get(field)))


def dedupe_warnings(warnings) -> list[OfficialWarning]:
    unique = {}
    for warning in warnings:
        if not isinstance(warning, dict):
            continue
        key = warning.get("id") or (
            warning.get("title", ""),
            warning.get("typeName", ""),
            warning.get("pubTime", ""),
            warning.get("color", ""),
        )
        current = unique.get(key)
        if current is None or warning.get("levelScore", 0) > current.get("levelScore", 0):
            unique[key] = warning
    return sorted(
        unique.values(),
        key=lambda warning: warning.get("levelScore", 0),
        reverse=True,
    )


class CountyAggregator:
    def __init__(self, locations: list[Room]):
        self.rooms_by_county = defaultdict(list)
        for room in locations:
            self.rooms_by_county[room.get("county", "")].append(room["name"])

    def aggregate(self, rooms_data: list[WeatherStats]) -> list[CountyRisk]:
        by_county = defaultdict(list)
        for room in rooms_data:
            by_county[room.get("county", "")].append(room)

        stats = []
        for county, rooms in by_county.items():
            warnings = dedupe_warnings(
                [warning for room in rooms for warning in room.get("officialWarnings", [])]
            )
            max_temp_source = room_with_extreme(rooms, "tmax")
            min_temp_source = room_with_extreme(rooms, "tmin", highest=False)
            max_rain_source = room_with_extreme(rooms, "maxRainHours")
            max_precip_source = room_with_extreme(rooms, "maxPrecip")
            daily_heat_source = room_with_extreme(rooms, "maxContDaily35")

            county_risk = {
                "name": county,
                "roomCount": len(self.rooms_by_county.get(county, rooms)),
                "warnedCount": len(rooms),
                "maxTemp": max_temp_source.get("tmax") if max_temp_source else None,
                "minTemp": min_temp_source.get("tmin") if min_temp_source else None,
                "maxCont40": max(to_number(room.get("maxCont40")) for room in rooms),
                "maxCont38": max(to_number(room.get("maxCont38")) for room in rooms),
                "maxCont37": max(to_number(room.get("maxCont37")) for room in rooms),
                "maxContDaily35": max(to_number(room.get("maxContDaily35")) for room in rooms),
                "maxContBelow0": max(to_number(room.get("maxContBelow0")) for room in rooms),
                "hoursAbove37": max(to_number(room.get("hoursAbove37")) for room in rooms),
                "hoursBelow5": max(to_number(room.get("hoursBelow5")) for room in rooms),
                "maxPrecip": max(to_number(room.get("maxPrecip")) for room in rooms),
                "maxDailyPrecip": max(to_number(room.get("maxDailyPrecip")) for room in rooms),
                "maxPrecip3h": max(to_number(room.get("maxPrecip3h")) for room in rooms),
                "maxPrecip6h": max(to_number(room.get("maxPrecip6h")) for room in rooms),
                "maxPrecip12h": max(to_number(room.get("maxPrecip12h")) for room in rooms),
                "maxPrecip24h": max(to_number(room.get("maxPrecip24h")) for room in rooms),
                "maxRainHours": max(to_number(room.get("maxRainHours")) for room in rooms),
                "maxWind": max(to_number(room.get("maxWind")) for room in rooms),
                "hasThunder": any(room.get("hasThunder") for room in rooms),
                "hasSnow": any(room.get("hasSnow") for room in rooms),
                "hasFreezing": any(room.get("hasFreezing") for room in rooms),
                "hasHail": any(room.get("hasHail") for room in rooms),
                "hasFogHaze": any(
                    room.get("hasFog") or room.get("hasHaze") or room.get("hasSand")
                    for room in rooms
                ),
                "officialWarnings": warnings[:5],
                "officialWarningLevel": warnings[0]["color"] if warnings else "",
                "officialWarningTitle": warnings[0]["title"] if warnings else "",
                "rooms": self.rooms_by_county.get(
                    county,
                    [room["name"] for room in rooms],
                ),
                "riskRooms": rooms,
                "maxTempSource": max_temp_source,
                "minTempSource": min_temp_source,
                "maxRainSource": max_rain_source,
                "maxPrecipSource": max_precip_source,
                "dailyHeatSource": daily_heat_source,
            }
            stats.append(county_risk)

        stats.sort(key=forecast_risk_score, reverse=True)
        return stats


def find_temp_dates(county_risk, threshold, high=True):
    if high and threshold == 35:
        source = county_risk.get("dailyHeatSource")
    elif high:
        source = county_risk.get("maxTempSource")
    else:
        source = county_risk.get("minTempSource")
    if not source:
        return []

    dates = []
    for day in source.get("dailySummary", []):
        temperature = to_number(day.get("tmax" if high else "tmin"), None)
        if temperature is None:
            continue
        if high and temperature > threshold:
            dates.append(day.get("date", ""))
        elif not high and temperature <= threshold:
            dates.append(day.get("date", ""))
    return sorted({date for date in dates if date})


def find_rain_dates(county_risk):
    source = county_risk.get("maxRainSource")
    if not source:
        return []
    return sorted(
        {
            day.get("date", "")
            for day in source.get("dailySummary", [])
            if to_number(day.get("precip")) > 0 and day.get("date")
        }
    )


def find_weather_dates(county_risk, keywords):
    dates = []
    for room in county_risk.get("riskRooms", []):
        for day in room.get("dailySummary", []):
            full_text = f"{day.get('textDay', '')}{day.get('textNight', '')}"
            if any(keyword in full_text for keyword in keywords):
                dates.append(day.get("date", ""))
    return sorted({date for date in dates if date})
