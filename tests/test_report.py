import unittest

from qweather_none_agent.report import ReportGenerator


def _generator():
    return ReportGenerator(
        [{"name": "A", "county": "C", "lon": 1, "lat": 2}],
        region="R",
    )


def _room(**overrides):
    data = {
        "name": "A",
        "county": "C",
        "tmax": 38,
        "tmin": 20,
        "maxCont40": 0,
        "maxCont38": 1,
        "maxCont37": 2,
        "maxContBelow0": 0,
        "hoursAbove37": 2,
        "hoursBelow5": 0,
        "maxPrecip": 0,
        "maxRainHours": 0,
        "maxWind": 0,
        "hasThunder": False,
        "hasSnow": False,
        "hasFreezing": False,
        "hasHail": False,
        "hasFog": False,
        "hasHaze": False,
        "hasSand": False,
        "dailySummary": [
            {
                "date": "2026-07-14",
                "tmax": 38,
                "tmin": 20,
                "precip": 0,
                "textDay": "晴",
                "textNight": "晴",
            }
        ],
    }
    data.update(overrides)
    return data


class ReportGeneratorTest(unittest.TestCase):
    def test_no_warning_report_does_not_crash(self):
        report = _generator().generate({
            "counties": [],
            "total": 1,
            "updateTime": "2026-07-14T00:00+08:00",
        })

        self.assertIn("暂无重大天气预警", report)

    def test_warning_without_significant_risk_does_not_crash(self):
        report = _generator().generate({
            "counties": [_room()],
            "total": 1,
            "updateTime": "2026-07-14T00:00+08:00",
        })

        self.assertIn("重点风险", report)
        self.assertIn("C", report)

    def test_failed_weather_data_is_reported_as_incomplete(self):
        report = _generator().generate({
            "counties": [],
            "total": 1,
            "failed": 1,
            "partialFailed": 1,
            "updateTime": "2026-07-14T00:00+08:00",
        })

        self.assertIn("数据获取失败", report)
        self.assertIn("数据获取不完整", report)
        self.assertNotIn("天气状况良好", report)

    def test_room_heading_and_risk_text_include_combined_hazards(self):
        report = _generator().generate({
            "counties": [
                _room(maxPrecip=11.1, maxRainHours=3, hasThunder=True),
            ],
            "total": 1,
            "updateTime": "2026-07-14T00:00+08:00",
        })

        self.assertIn("C（橙色高温、强降水、连续降雨、雷暴）", report)
        self.assertIn("最大小时降水11.1mm", report)
        self.assertIn("伴有雷暴", report)


if __name__ == "__main__":
    unittest.main()
