import unittest

from weather_analysis.report import ReportGenerator, _compact_warning_title


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
    def test_compact_warning_title_removes_publish_word(self):
        self.assertEqual(
            "示例区域02气象台高温红色预警",
            _compact_warning_title("示例区域02气象台发布高温红色预警"),
        )

    def test_no_warning_report_does_not_crash(self):
        report = _generator().generate(
            {
                "counties": [],
                "total": 1,
                "updateTime": "2026-07-14T00:00+08:00",
            }
        )

        self.assertIn("暂无机房预警", report)

    def test_warning_without_significant_risk_does_not_crash(self):
        report = _generator().generate(
            {
                "counties": [_room()],
                "total": 1,
                "updateTime": "2026-07-14T00:00+08:00",
            }
        )

        self.assertIn("重点风险", report)
        self.assertIn("C", report)

    def test_yellow_risk_is_counted_as_a_room_alert(self):
        report = _generator().generate(
            {
                "counties": [_room(tmax=34, maxWind=8)],
                "total": 1,
                "updateTime": "2026-07-14T00:00+08:00",
            }
        )

        self.assertIn("达到机房预警标准", report)

    def test_official_warning_is_rendered_only_as_a_suggestion(self):
        report = _generator().generate(
            {
                "counties": [],
                "total": 1,
                "updateTime": "2026-07-14T00:00+08:00",
                "officialSuggestions": [
                    {
                        "county": "C",
                        "warnings": [{"title": "C气象台发布高温红色预警"}],
                    }
                ],
            }
        )

        self.assertIn("暂无机房预警", report)
        self.assertIn("官方预警建议（不参与等级）：C：C气象台高温红色预警", report)

    def test_failed_weather_data_is_reported_as_incomplete(self):
        report = _generator().generate(
            {
                "counties": [],
                "total": 1,
                "failed": 1,
                "partialFailed": 1,
                "updateTime": "2026-07-14T00:00+08:00",
            }
        )

        self.assertIn("数据获取失败", report)
        self.assertIn("数据获取不完整", report)
        self.assertNotIn("天气状况良好", report)

    def test_room_heading_and_risk_text_include_combined_hazards(self):
        report = _generator().generate(
            {
                "counties": [
                    _room(maxPrecip=11.1, maxRainHours=3, hasThunder=True),
                ],
                "total": 1,
                "updateTime": "2026-07-14T00:00+08:00",
            }
        )

        self.assertIn("C（橙色高温、强降水）", report)
        risk_section = report.split("二、重点机房")[0]
        self.assertNotIn("最大小时降水", risk_section)
        self.assertIn("伴有短时强降雨", report)
        self.assertIn("伴有连续降雨", report)
        self.assertIn("伴有雷暴", report)

    def test_room_lines_include_focus_period_reason(self):
        room = _room(
            maxPrecip=11.1,
            maxRainHours=3,
            hasThunder=True,
            dailySummary=[
                {
                    "date": "2026-07-14",
                    "tmax": 38,
                    "tmin": 20,
                    "precip": 0,
                    "textDay": "晴",
                    "textNight": "晴",
                },
                {
                    "date": "2026-07-15",
                    "tmax": 36,
                    "tmin": 20,
                    "precip": 5,
                    "textDay": "雷阵雨",
                    "textNight": "雨",
                },
            ],
        )
        report = _generator().generate(
            {
                "counties": [room],
                "total": 1,
                "updateTime": "2026-07-14T00:00+08:00",
            }
        )

        self.assertIn("A：7月14日高温", report)
        self.assertIn("7月15日连续降雨", report)

    def test_official_warning_time_is_used_when_forecast_period_is_missing(self):
        room = _room(
            tmax=None,
            dailySummary=[],
            officialWarnings=[
                {
                    "typeName": "高温",
                    "pubTime": "2026-07-14T08:00+08:00",
                }
            ],
        )

        self.assertEqual("7月14日高温预警", _generator()._room_focus_period(room))


if __name__ == "__main__":
    unittest.main()
