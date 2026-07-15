import unittest

from weather_analysis.warning_rules import (
    evaluate_hazards,
    is_forecast_significant,
    report_level,
    risk_score,
)


def _hazards(data):
    return {(h["name"], h["level"]) for h in evaluate_hazards(data)}


class WarningRulesTest(unittest.TestCase):
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
        hazards = _hazards({"maxPrecip3h": 50.1})

        self.assertIn(("暴雨", "橙色"), hazards)

    def test_exact_rainstorm_thresholds_do_not_trigger(self):
        self.assertNotIn(("暴雨", "橙色"), _hazards({"maxPrecip3h": 50}))
        self.assertNotIn(("暴雨", "红色"), _hazards({"maxPrecip3h": 100}))

    def test_report_level_uses_highest_hazard_level(self):
        level = report_level(
            [
                {"maxWind": 8},
                {"tmax": 41},
            ]
        )

        self.assertEqual("红色预警", level)

    def test_official_warning_can_raise_hazard_level(self):
        hazards = _hazards(
            {
                "officialWarnings": [
                    {
                        "typeName": "雷电",
                        "color": "橙色",
                        "levelScore": 3,
                        "title": "雷电橙色预警",
                    }
                ]
            }
        )

        self.assertIn(("雷暴", "橙色"), hazards)

    def test_official_warning_alone_is_not_a_forecast_risk(self):
        warning_only = {
            "officialWarnings": [{"typeName": "高温", "levelScore": 4, "title": "高温红色预警"}]
        }

        self.assertFalse(is_forecast_significant(warning_only))
        self.assertTrue(is_forecast_significant({"tmax": 38, **warning_only}))

    def test_all_official_warning_types_are_kept(self):
        hazards = _hazards(
            {
                "officialWarnings": [
                    {"typeName": "高温", "levelScore": 4},
                    {"typeName": "暴雨", "levelScore": 3},
                ]
            }
        )

        self.assertIn(("红色高温", "红色"), hazards)
        self.assertIn(("暴雨", "橙色"), hazards)

    def test_risk_sorting_never_places_orange_above_red(self):
        red = {"tmax": 41, "warnedCount": 1}
        orange = {
            "tmax": 38,
            "warnedCount": 100,
            "maxCont37": 10,
            "maxRainHours": 10,
            "maxPrecip": 30,
        }

        self.assertGreater(risk_score(red), risk_score(orange))

    def test_missing_minimum_temperature_does_not_create_icing_warning(self):
        hazards = _hazards({"tmin": None, "maxPrecip24h": 5})

        self.assertNotIn(("道路结冰", "黄色"), hazards)

    def test_official_high_temperature_warning_dedupes_local_heat_label(self):
        hazards = _hazards(
            {
                "tmax": 39,
                "officialWarnings": [
                    {
                        "typeName": "高温",
                        "color": "红色",
                        "levelScore": 4,
                        "title": "高温红色预警",
                    }
                ],
            }
        )

        self.assertIn(("红色高温", "红色"), hazards)
        self.assertNotIn(("橙色高温", "橙色"), hazards)


if __name__ == "__main__":
    unittest.main()
