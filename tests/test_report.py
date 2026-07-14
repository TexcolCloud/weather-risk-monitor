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

        self.assertIn("C（橙色高温、强降水）", report)
        self.assertIn("最大小时降水11.1mm", report)
        self.assertIn("伴有雷暴", report)

    def test_top_rooms_are_not_evenly_capped_at_three_per_county(self):
        locations = [
            {"name": f"A{i}", "county": "A", "lon": 1, "lat": 1}
            for i in range(8)
        ] + [
            {"name": f"B{i}", "county": "B", "lon": 2, "lat": 2}
            for i in range(8)
        ]
        generator = ReportGenerator(locations, region="R")
        rooms = [
            _room(name=f"A{i}", county="A", tmax=41, maxCont37=8)
            for i in range(8)
        ] + [
            _room(name=f"B{i}", county="B", tmax=38, maxCont37=2)
            for i in range(8)
        ]
        focus_counties = [{"name": "A"}, {"name": "B"}]

        selected = generator._select_top_rooms(rooms, focus_counties)

        self.assertEqual(10, len(selected))
        self.assertGreater(sum(1 for r in selected if r["county"] == "A"), 3)

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
        report = _generator().generate({
            "counties": [room],
            "total": 1,
            "updateTime": "2026-07-14T00:00+08:00",
        })

        self.assertIn("A：7月14日37℃以上高温", report)
        self.assertIn("7月15日连续降雨3小时", report)


if __name__ == "__main__":
    unittest.main()
