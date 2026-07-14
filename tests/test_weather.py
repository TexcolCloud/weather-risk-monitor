import unittest
from unittest.mock import patch

from weather_analysis.qweather_client import QWeatherClient
from weather_analysis.weather import WeatherService


class WeatherServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_official_warning_survives_daily_forecast_failure(self):
        async def fake_fetch(client, url, params, lat, lon, endpoint, ttl):
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
        self.assertEqual(1, result["warned"])
        self.assertEqual("红色", result["counties"][0]["officialWarningLevel"])

    async def test_empty_hourly_and_failed_warning_sources_are_reported(self):
        async def fake_fetch(client, url, params, lat, lon, endpoint, ttl):
            if endpoint == "7d":
                return {
                    "code": "200",
                    "updateTime": "2026-07-14T08:00+08:00",
                    "daily": [
                        {
                            "fxDate": "2026-07-14",
                            "tempMax": "38",
                            "tempMin": "20",
                            "precip": "0",
                            "windScaleDay": "1",
                            "windScaleNight": "1",
                        }
                    ],
                }
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


if __name__ == "__main__":
    unittest.main()
