import unittest

from qweather_none_agent.standards import evaluate_hazards, report_level
from qweather_none_agent.weather import WeatherTool


def _hazards(data):
    return {(h["name"], h["level"]) for h in evaluate_hazards(data)}


class StandardsTest(unittest.TestCase):
    def test_high_temperature_levels_follow_warning_thresholds(self):
        self.assertIn(("红色高温", "红色"), _hazards({"tmax": 41}))
        self.assertIn(("橙色高温", "橙色"), _hazards({"tmax": 38}))
        self.assertIn(("高温", "黄色"), _hazards({"tmax": 36, "maxContDaily35": 3}))

    def test_exact_high_temperature_thresholds_do_not_trigger(self):
        self.assertNotIn(("红色高温", "红色"), _hazards({"tmax": 40}))
        self.assertNotIn(("橙色高温", "橙色"), _hazards({"tmax": 37}))
        self.assertFalse(_hazards({"tmax": 35, "maxContDaily35": 0}))

    def test_wind_level_uses_national_scale_thresholds(self):
        hazards = _hazards({"maxWind": 8})

        self.assertIn(("大风", "黄色"), hazards)
        self.assertNotIn(("大风", "红色"), hazards)

    def test_rainstorm_uses_rolling_precipitation_windows(self):
        hazards = _hazards({"maxPrecip3h": 50})

        self.assertIn(("暴雨", "橙色"), hazards)

    def test_report_level_uses_highest_hazard_level(self):
        level = report_level([
            {"maxWind": 8},
            {"tmax": 41},
        ])

        self.assertEqual("红色预警", level)

    def test_official_warning_can_raise_hazard_level(self):
        hazards = _hazards({
            "officialWarnings": [{
                "typeName": "雷电",
                "color": "橙色",
                "levelScore": 3,
                "title": "雷电橙色预警",
            }]
        })

        self.assertIn(("雷电", "橙色"), hazards)

    def test_official_high_temperature_warning_dedupes_local_heat_label(self):
        hazards = _hazards({
            "tmax": 39,
            "officialWarnings": [{
                "typeName": "高温",
                "color": "红色",
                "levelScore": 4,
                "title": "高温红色预警",
            }]
        })

        self.assertIn(("红色高温", "红色"), hazards)
        self.assertNotIn(("橙色高温", "橙色"), hazards)

    def test_weather_stats_compute_rolling_precipitation(self):
        daily = [{
            "fxDate": "2026-07-14",
            "tempMax": "20",
            "tempMin": "10",
            "precip": "60",
            "windScaleDay": "1-2",
            "windScaleNight": "1-2",
        }]
        hourly = [
            {"temp": "20", "precip": "20", "text": "雨"},
            {"temp": "20", "precip": "15", "text": "雨"},
            {"temp": "20", "precip": "15", "text": "雨"},
        ]

        stats = WeatherTool._compute_stats(daily, hourly)

        self.assertEqual(50, stats["maxPrecip3h"])


if __name__ == "__main__":
    unittest.main()
