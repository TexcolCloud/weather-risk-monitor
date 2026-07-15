import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from weather_analysis.qweather_client import QWeatherClient
from weather_analysis.weather import WeatherService


TARGET = datetime(2026, 7, 14, 8, tzinfo=ZoneInfo("Asia/Shanghai"))
ROOMS = [{"name": "A", "county": "C", "lat": 30.0, "lon": 111.0}]


def _hours(temperatures=(38, 36, 35), precipitation=(0, 0, 0)):
    return [
        {
            "fxTime": f"2026-07-14T{hour:02}:00+08:00",
            "temp": str(temperature),
            "precip": str(rain),
            "windScale": "1-2",
            "text": "小雨" if rain else "晴",
        }
        for hour, temperature, rain in zip((8, 9, 10), temperatures, precipitation)
    ]


class HourlyRiskTest(unittest.IsolatedAsyncioTestCase):
    async def test_immediate_and_three_hour_risks_are_reported_separately(self):
        async def fake_fetch(client, url, params, lat, lon, endpoint, ttl):
            if endpoint == "168h":
                return {"code": "200", "updateTime": TARGET.isoformat(), "hourly": _hours()}
            return {"code": "200", "warning": []}

        with patch.object(QWeatherClient, "fetch", new=fake_fetch):
            result = await WeatherService.run_hourly_risk(ROOMS, TARGET)

        self.assertEqual(["A"], [room["name"] for room in result["immediateRisks"]])
        self.assertEqual(["A"], [room["name"] for room in result["outlookRisks"]])
        self.assertEqual("2026-07-14T08:00:00+08:00", result["targetStart"])
        self.assertEqual("2026-07-14T09:00:00+08:00", result["immediateEnd"])
        self.assertEqual("2026-07-14T11:00:00+08:00", result["outlookEnd"])

    async def test_three_hour_rainstorm_does_not_become_immediate_risk(self):
        async def fake_fetch(client, url, params, lat, lon, endpoint, ttl):
            if endpoint == "168h":
                return {"code": "200", "hourly": _hours((28, 28, 28), (20, 20, 20))}
            return {"code": "200", "warning": []}

        with patch.object(QWeatherClient, "fetch", new=fake_fetch):
            result = await WeatherService.run_hourly_risk(ROOMS, TARGET)

        self.assertEqual([], result["immediateRisks"])
        self.assertEqual(["A"], [room["name"] for room in result["outlookRisks"]])
        self.assertEqual(60, result["outlookRisks"][0]["stats"]["maxPrecip3h"])

    async def test_official_warning_does_not_create_hourly_risk_without_forecast_data(self):
        async def fake_fetch(client, url, params, lat, lon, endpoint, ttl):
            if endpoint == "168h":
                return None
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

        with patch.object(QWeatherClient, "fetch", new=fake_fetch):
            result = await WeatherService.run_hourly_risk(ROOMS, TARGET)

        self.assertEqual(1, result["failed"])
        self.assertEqual([], result["immediateRisks"])

    async def test_official_warning_is_attached_to_data_derived_risk(self):
        async def fake_fetch(client, url, params, lat, lon, endpoint, ttl):
            if endpoint == "168h":
                return {"code": "200", "hourly": _hours()}
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

        with patch.object(QWeatherClient, "fetch", new=fake_fetch):
            result = await WeatherService.run_hourly_risk(ROOMS, TARGET)

        self.assertEqual(["A"], [room["name"] for room in result["immediateRisks"]])
        self.assertEqual(38, result["immediateRisks"][0]["stats"]["tmax"])
        self.assertEqual("红色", result["immediateRisks"][0]["stats"]["officialWarningLevel"])
