import unittest

from qweather_none_agent.weather import WeatherTool, _normalize_warnings


class WeatherToolTest(unittest.TestCase):
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
        hourly = [{"temp": "20", "precip": "0", "text": "雷暴"}]

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
            {"temp": "37", "precip": "0", "text": "晴"},
            {"temp": "37.1", "precip": "0", "text": "晴"},
        ]

        stats = WeatherTool._compute_stats(daily, hourly)

        self.assertEqual(1, stats["maxCont37"])
        self.assertEqual(1, stats["maxContDaily35"])

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
