import unittest
from unittest.mock import patch

from qweather_none_agent.weather import WeatherTool, _normalize_warnings


class WeatherToolTest(unittest.IsolatedAsyncioTestCase):
    def test_night_wind_scale_is_included(self):
        daily = [
            {
                "fxDate": "2026-07-14",
                "tempMax": "20",
                "tempMin": "10",
                "precip": "0",
                "windScaleDay": "1-2",
                "windScaleNight": "6-7",
            }
        ]

        stats = WeatherTool._compute_stats(daily, [])

        self.assertEqual(7, stats["maxWind"])

    def test_weather_keywords_set_warning_flags(self):
        daily = [
            {
                "fxDate": "2026-07-14",
                "tempMax": "20",
                "tempMin": "10",
                "precip": "0",
                "windScaleDay": "1-2",
                "windScaleNight": "1-2",
            }
        ]
        hourly = [{
            "fxTime": "2026-07-14T00:00+08:00",
            "temp": "20",
            "precip": "0",
            "text": "雷暴",
        }]

        stats = WeatherTool._compute_stats(daily, hourly)

        self.assertTrue(stats["hasThunder"])

    def test_high_temperature_duration_uses_strict_above_threshold(self):
        daily = [
            {
                "fxDate": "2026-07-14",
                "tempMax": "35",
                "tempMin": "20",
                "precip": "0",
                "windScaleDay": "1-2",
                "windScaleNight": "1-2",
            },
            {
                "fxDate": "2026-07-15",
                "tempMax": "36",
                "tempMin": "20",
                "precip": "0",
                "windScaleDay": "1-2",
                "windScaleNight": "1-2",
            },
        ]
        hourly = [
            {
                "fxTime": "2026-07-14T00:00+08:00",
                "temp": "37",
                "precip": "0",
                "text": "晴",
            },
            {
                "fxTime": "2026-07-14T01:00+08:00",
                "temp": "37.1",
                "precip": "0",
                "text": "晴",
            },
        ]

        stats = WeatherTool._compute_stats(daily, hourly)

        self.assertEqual(1, stats["maxCont37"])
        self.assertEqual(1, stats["maxContDaily35"])

    def test_hourly_gap_breaks_continuous_duration_and_rolling_window(self):
        daily = [{
            "fxDate": "2026-07-14",
            "tempMax": "38",
            "tempMin": "20",
            "precip": "0",
            "windScaleDay": "1",
            "windScaleNight": "1",
        }]
        hourly = [
            {
                "fxTime": "2026-07-14T10:00+08:00",
                "temp": "38",
                "precip": "20",
                "text": "雨",
            },
            {
                "fxTime": "2026-07-14T15:00+08:00",
                "temp": "38",
                "precip": "20",
                "text": "雨",
            },
        ]

        stats = WeatherTool._compute_stats(daily, hourly)

        self.assertEqual(1, stats["maxCont37"])
        self.assertEqual(1, stats["maxRainHours"])
        self.assertEqual(20, stats["maxPrecip3h"])
        self.assertFalse(stats["hourlyDataComplete"])

    def test_daily_weather_text_is_used_when_hourly_data_is_missing(self):
        daily = [{
            "fxDate": "2026-07-14",
            "tempMax": "20",
            "tempMin": "10",
            "precip": "0",
            "textDay": "雷阵雨",
            "textNight": "雾",
            "windScaleDay": "1",
            "windScaleNight": "1",
        }]

        stats = WeatherTool._compute_stats(daily, None)

        self.assertTrue(stats["hasThunder"])
        self.assertTrue(stats["hasFog"])

    async def test_official_warning_survives_daily_forecast_failure(self):
        async def fake_fetch(client, sem, url, params, lat, lon, endpoint, ttl):
            if endpoint == "warning":
                return {
                    "code": "200",
                    "updateTime": "2026-07-14T08:00+08:00",
                    "warning": [{
                        "id": "warning-1",
                        "title": "高温红色预警",
                        "typeName": "高温",
                        "severityColor": "Red",
                    }],
                }
            return None

        locations = [{
            "name": "A",
            "county": "C",
            "lat": 30.0,
            "lon": 111.0,
        }]
        with patch.object(WeatherTool, "_fetch", new=fake_fetch):
            result = await WeatherTool.run(locations)

        self.assertEqual(1, result["failed"])
        self.assertEqual(1, result["warned"])
        self.assertEqual("红色", result["counties"][0]["officialWarningLevel"])

    async def test_empty_hourly_and_failed_warning_sources_are_reported(self):
        async def fake_fetch(client, sem, url, params, lat, lon, endpoint, ttl):
            if endpoint == "7d":
                return {
                    "code": "200",
                    "updateTime": "2026-07-14T08:00+08:00",
                    "daily": [{
                        "fxDate": "2026-07-14",
                        "tempMax": "38",
                        "tempMin": "20",
                        "precip": "0",
                        "windScaleDay": "1",
                        "windScaleNight": "1",
                    }],
                }
            if endpoint == "168h":
                return {"code": "200", "hourly": []}
            return None

        locations = [{
            "name": "A",
            "county": "C",
            "lat": 30.0,
            "lon": 111.0,
        }]
        with patch.object(WeatherTool, "_fetch", new=fake_fetch):
            result = await WeatherTool.run(locations)

        self.assertEqual(1, result["partialFailed"])
        self.assertEqual(1, result["warningFailed"])
        self.assertEqual(["A"], result["partialFailedRooms"])

    def test_normalize_qweather_warning_shapes(self):
        v7 = {
            "warning": [{
                "id": "1",
                "title": "雷电橙色预警",
                "typeName": "雷电",
                "severityColor": "Orange",
                "text": "可能发生雷电活动",
            }]
        }
        v1 = {
            "alerts": [{
                "identifier": "2",
                "headline": "暴雨红色预警",
                "eventType": "暴雨",
                "color": {"code": "red"},
                "description": "强降水持续",
            }]
        }

        self.assertEqual("橙色", _normalize_warnings(v7)[0]["color"])
        self.assertEqual("暴雨", _normalize_warnings(v1)[0]["typeName"])
        self.assertEqual(4, _normalize_warnings(v1)[0]["levelScore"])


if __name__ == "__main__":
    unittest.main()
