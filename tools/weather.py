
import asyncio
import httpx
from config import QWEATHER_API_KEY, QWEATHER_BASE_URL, FORECAST_DAYS, HOURLY_HOURS

MAX_CONCURRENT = 50

WEATHER_KEYWORDS = {
    "thunder": ("雷", "雷暴"),
    "snow": ("雪",),
    "freezing": ("冻雨", "冰粒"),
    "hail": ("冰雹",),
    "fog": ("雾",),
    "haze": ("霾",),
    "sand": ("沙尘暴", "沙尘", "扬沙"),
}

WARNING_KEYS = [
    "hasThunder", "hasSnow", "hasFreezing", "hasHail",
    "hasFog", "hasHaze", "hasSand",
]


class WeatherTool:
    name = "get_weather_data"
    description = "批量获取多个机房的7天逐日+逐时预报数据。"

    parameters = {
        "type": "object",
        "properties": {
            "counties": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "机房名称"},
                        "location": {"type": "string", "description": "经纬度"},
                        "county": {"type": "string", "description": "所属县区"}
                    },
                    "required": ["name", "location"]
                },
                "description": "机房列表"
            }
        },
        "required": ["counties"]
    }

    @staticmethod
    def tool_spec():
        return {
            "type": "function",
            "function": {
                "name": WeatherTool.name,
                "description": WeatherTool.description,
                "parameters": WeatherTool.parameters
            }
        }

    @staticmethod
    def _loc(c):
        if "location" in c:
            return c["location"]
        return f"{c['lon']:.2f},{c['lat']:.2f}"

    @staticmethod
    async def _fetch(client, sem, url, params):
        async with sem:
            try:
                resp = await client.get(url, params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                return data if data.get("code") == "200" else None
            except Exception:
                return None

    @staticmethod
    def _compute_stats(daily, hourly):
        tmax = max(int(d["tempMax"]) for d in daily)
        tmin = min(int(d["tempMin"]) for d in daily)
        total_precip = sum(float(d["precip"]) for d in daily)
        rain_days = sum(1 for d in daily if float(d["precip"]) > 0)
        max_wind = max(int(d["windScaleDay"].split("-")[-1]) for d in daily)

        daily_summary = []
        for d in daily:
            daily_summary.append({
                "date": d["fxDate"],
                "tmax": int(d["tempMax"]), "tmin": int(d["tempMin"]),
                "textDay": d["textDay"], "textNight": d["textNight"],
                "windDay": d["windScaleDay"], "windNight": d["windScaleNight"],
                "precip": float(d["precip"]), "humidity": d["humidity"],
            })

        hours_above_40 = max_cont_40 = cur_40 = 0
        hours_above_38 = max_cont_38 = cur_38 = 0
        hours_above_37 = max_cont_37 = cur_37 = 0
        hours_above_35 = 0
        hours_below_0 = hours_below_5 = max_cont_below0 = cur_below0 = 0
        max_rain_hours = cur_rain = max_precip = 0
        flags = {k: False for k in WARNING_KEYS}

        if hourly:
            for h in hourly:
                t = float(h["temp"])
                p = float(h["precip"])
                txt = h["text"]
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
        return (stats["tmax"] >= 37 or stats["tmin"] <= 0
                or stats["maxPrecip"] >= 16 or stats["maxWind"] >= 6
                or any(stats[k] for k in WARNING_KEYS))

    @staticmethod
    async def run(counties):
        sem = asyncio.Semaphore(MAX_CONCURRENT)
        headers = {"X-QW-API-KEY": QWEATHER_API_KEY}
        params_base = {"lang": "zh"}
        county_map = {c["name"]: c for c in counties}

        async with httpx.AsyncClient(headers=headers, limits=httpx.Limits(
            max_connections=MAX_CONCURRENT, max_keepalive_connections=20
        )) as client:
            daily_tasks = {}
            for c in counties:
                url = f"{QWEATHER_BASE_URL}/{FORECAST_DAYS}"
                p = {**params_base, "location": WeatherTool._loc(c)}
                daily_tasks[c["name"]] = WeatherTool._fetch(client, sem, url, p)

            daily_results = dict(zip(
                daily_tasks.keys(),
                await asyncio.gather(*daily_tasks.values())
            ))

            hourly_tasks = {}
            date_ranges = {}
            for name, data in daily_results.items():
                if not data:
                    continue
                c = county_map[name]
                url = f"{QWEATHER_BASE_URL}/{HOURLY_HOURS}h"
                p = {**params_base, "location": WeatherTool._loc(c)}
                d = data["daily"]
                date_ranges[name] = (d[0]["fxDate"], d[-1]["fxDate"])
                hourly_tasks[name] = WeatherTool._fetch(client, sem, url, p)

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
            if not data:
                continue
            if not result["updateTime"]:
                result["updateTime"] = data.get("updateTime")

            daily = data["daily"]
            hourly = None
            hr = hourly_results.get(name)
            if hr:
                start, end = date_ranges[name]
                hourly = [h for h in hr["hourly"]
                          if start <= h["fxTime"][:10] <= end]

            stats = WeatherTool._compute_stats(daily, hourly)
            if WeatherTool._has_warning(stats):
                result["warned"] += 1
                result["counties"].append({
                    "name": name,
                    "county": c.get("county", ""),
                    **stats,
                })

        return result
