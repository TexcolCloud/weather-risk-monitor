import unittest
from collections import Counter
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from weather_analysis.qweather_client import QWeatherClient
from weather_analysis.weather import WeatherService


START = datetime(2026, 7, 14, tzinfo=ZoneInfo("Asia/Shanghai"))


def _hourly(hours: int = 168, temp: str = "25", precip: str = "0", text: str = "晴"):
    return [
        {
            "fxTime": (START + timedelta(hours=index)).isoformat(),
            "temp": temp,
            "precip": precip,
            "windScale": "1-2",
            "text": text,
        }
        for index in range(hours)
    ]


class WeatherServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_partial_hourly_failure_does_not_abort_successful_rooms(self):
        async def fake_fetch(client, url, params, lat, lon, endpoint, ttl):
            if endpoint == "168h":
                if lon == 112.0:
                    return None
                return {
                    "code": "200",
                    "hourly": _hourly(),
                }
            return {"code": "200", "warning": []}

        locations = [
            {"name": "A", "county": "C1", "lat": 30.0, "lon": 111.0},
            {"name": "B", "county": "C2", "lat": 31.0, "lon": 112.0},
        ]
        with patch.object(QWeatherClient, "fetch", new=fake_fetch):
            result = await WeatherService.run(locations)

        self.assertEqual(1, result["failed"])
        self.assertEqual(["B"], result["failedRooms"])

    async def test_official_warning_does_not_replace_missing_forecast_data(self):
        async def fake_fetch(client, url, params, lat, lon, endpoint, ttl):
            if endpoint == "168h":
                return None
            if endpoint == "warning":
                return {
                    "code": "200",
                    "updateTime": "2026-07-14T08:00+08:00",
                    "warning": [
                        {
                            "id": "warning-1",
                            "title": "高温红色预警",
                            "typeName": "高温",
                            "severityColor": "Red",
                        }
                    ],
                }
            return None

        locations = [
            {
                "name": "A",
                "county": "C",
                "lat": 30.0,
                "lon": 111.0,
            }
        ]
        with patch.object(QWeatherClient, "fetch", new=fake_fetch):
            result = await WeatherService.run(locations)

        self.assertEqual(1, result["failed"])
        self.assertEqual(0, result["warned"])
        self.assertEqual([], result["counties"])
        self.assertEqual("C", result["auxiliaryWarnings"][0]["county"])

    async def test_identical_query_locations_share_weather_requests(self):
        calls = Counter()

        async def fake_fetch(client, url, params, lat, lon, endpoint, ttl):
            calls[endpoint] += 1
            if endpoint == "168h":
                return {"code": "200", "hourly": _hourly(temp="20")}
            return {"code": "200", "warning": []}

        locations = [
            {"name": "A", "county": "C", "lat": 30.0001, "lon": 111.0001},
            {"name": "B", "county": "C", "lat": 30.0002, "lon": 111.0002},
        ]
        with patch.object(QWeatherClient, "fetch", new=fake_fetch):
            await WeatherService.run(locations)

        self.assertEqual(1, calls["168h"])
        self.assertEqual(1, calls["warning"])
        self.assertEqual(0, calls["7d"])

    async def test_empty_hourly_and_failed_warning_sources_are_reported(self):
        async def fake_fetch(client, url, params, lat, lon, endpoint, ttl):
            if endpoint == "168h":
                return {"code": "200", "hourly": []}
            return None

        locations = [
            {
                "name": "A",
                "county": "C",
                "lat": 30.0,
                "lon": 111.0,
            }
        ]
        with patch.object(QWeatherClient, "fetch", new=fake_fetch):
            result = await WeatherService.run(locations)

        self.assertEqual(1, result["partialFailed"])
        self.assertEqual(1, result["warningFailed"])
        self.assertEqual(["A"], result["partialFailedRooms"])

    async def test_official_warning_is_a_suggestion_not_a_room_alert(self):
        async def fake_fetch(client, url, params, lat, lon, endpoint, ttl):
            if endpoint == "168h":
                return {"code": "200", "hourly": _hourly()}
            return {
                "code": "200",
                "warning": [
                    {
                        "title": "C气象台高温红色预警",
                        "typeName": "高温",
                        "severityColor": "Red",
                    }
                ],
            }

        locations = [{"name": "A", "county": "C", "lat": 30.0, "lon": 111.0}]
        with patch.object(QWeatherClient, "fetch", new=fake_fetch):
            result = await WeatherService.run(locations)

        self.assertEqual(0, result["warned"])
        self.assertEqual([], result["counties"])
        self.assertEqual("C", result["officialSuggestions"][0]["county"])


if __name__ == "__main__":
    unittest.main()
