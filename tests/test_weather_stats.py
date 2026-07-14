import unittest

from qweather_none_agent.weather_stats import compute_weather_stats


def _daily(**overrides):
    data = {
        "fxDate": "2026-07-14",
        "tempMax": "20",
        "tempMin": "10",
        "precip": "0",
        "windScaleDay": "1-2",
        "windScaleNight": "1-2",
    }
    data.update(overrides)
    return data


class WeatherStatsTest(unittest.TestCase):
    def test_night_wind_scale_is_included(self):
        stats = compute_weather_stats(
            [_daily(windScaleNight="6-7")],
            [],
        )

        self.assertEqual(7, stats["maxWind"])

    def test_weather_keywords_set_warning_flags(self):
        hourly = [
            {
                "fxTime": "2026-07-14T00:00+08:00",
                "temp": "20",
                "precip": "0",
                "text": "雷暴",
            }
        ]

        stats = compute_weather_stats([_daily()], hourly)

        self.assertTrue(stats["hasThunder"])

    def test_high_temperature_duration_uses_strict_above_threshold(self):
        daily = [
            _daily(tempMax="35"),
            _daily(fxDate="2026-07-15", tempMax="36"),
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

        stats = compute_weather_stats(daily, hourly)

        self.assertEqual(1, stats["maxCont37"])
        self.assertEqual(1, stats["maxContDaily35"])

    def test_hourly_gap_breaks_continuous_duration_and_rolling_window(self):
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

        stats = compute_weather_stats([_daily(tempMax="38")], hourly)

        self.assertEqual(1, stats["maxCont37"])
        self.assertEqual(1, stats["maxRainHours"])
        self.assertEqual(20, stats["maxPrecip3h"])
        self.assertFalse(stats["hourlyDataComplete"])

    def test_daily_weather_text_is_used_when_hourly_data_is_missing(self):
        daily = [_daily(textDay="雷阵雨", textNight="雾")]

        stats = compute_weather_stats(daily, None)

        self.assertTrue(stats["hasThunder"])
        self.assertTrue(stats["hasFog"])

    def test_rolling_precipitation_is_computed(self):
        hourly = [
            {
                "fxTime": f"2026-07-14T0{index}:00+08:00",
                "temp": "20",
                "precip": precip,
                "text": "雨",
            }
            for index, precip in enumerate(("20", "15", "15"))
        ]

        stats = compute_weather_stats([_daily(precip="60")], hourly)

        self.assertEqual(50, stats["maxPrecip3h"])


if __name__ == "__main__":
    unittest.main()
