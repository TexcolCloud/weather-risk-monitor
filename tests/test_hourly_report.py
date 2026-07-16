import unittest

from weather_analysis.hourly_report import HourlyReportGenerator


class HourlyReportTest(unittest.TestCase):
    def test_report_keeps_immediate_and_outlook_time_ranges_separate(self):
        result = {
            "targetStart": "2026-07-14T08:00:00+08:00",
            "immediateEnd": "2026-07-14T09:00:00+08:00",
            "outlookEnd": "2026-07-14T11:00:00+08:00",
            "total": 1,
            "immediateRisks": [
                {
                    "name": "A",
                    "county": "C",
                    "riskTime": "2026-07-14T08:00:00+08:00",
                    "temperature": 41,
                    "weatherText": "晴",
                    "stats": {"tmax": 41, "officialWarnings": []},
                }
            ],
            "outlookRisks": [],
        }

        report = HourlyReportGenerator("示例区域").generate(result)

        self.assertIn("下一小时预警（08:00-09:00）", report)
        self.assertIn("未来3小时预警过程（08:00-11:00）", report)
        self.assertIn("A：红色高温；08:00温度41℃", report)

    def test_report_lists_every_risk_room(self):
        risks = [
            {
                "name": f"A{index}",
                "county": "C",
                "riskTime": "2026-07-14T08:00:00+08:00",
                "temperature": 41,
                "stats": {"tmax": 41, "officialWarnings": []},
            }
            for index in range(11)
        ]
        result = {
            "targetStart": "2026-07-14T08:00:00+08:00",
            "immediateEnd": "2026-07-14T09:00:00+08:00",
            "outlookEnd": "2026-07-14T11:00:00+08:00",
            "total": 11,
            "immediateRisks": risks,
            "outlookRisks": [],
        }

        report = HourlyReportGenerator("示例区域").generate(result)

        self.assertIn("下一小时发现11个预警机房", report)
        self.assertIn("A9", report)
        self.assertIn("A10：", report)
        self.assertNotIn("其余1个高风险机房", report)

    def test_empty_sections_explain_the_yellow_threshold(self):
        result = {
            "targetStart": "2026-07-14T08:00:00+08:00",
            "immediateEnd": "2026-07-14T09:00:00+08:00",
            "outlookEnd": "2026-07-14T11:00:00+08:00",
            "total": 1,
            "immediateRisks": [],
            "outlookRisks": [],
        }

        report = HourlyReportGenerator("示例区域").generate(result)

        self.assertIn("暂无达到黄色及以上数据阈值的机房", report)
        self.assertIn("暂无达到黄色及以上数据阈值的预警过程", report)
