import unittest

from qweather_none_agent.weather import WeatherTool


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


if __name__ == "__main__":
    unittest.main()
