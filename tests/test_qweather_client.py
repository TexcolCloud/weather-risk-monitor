import unittest

from weather_analysis.qweather_client import QWeatherClient, normalize_warnings


class QWeatherClientTest(unittest.TestCase):
    def test_rate_limit_must_be_positive(self):
        with self.assertRaises(ValueError):
            QWeatherClient("test-key", max_requests_per_second=0)

    def test_normalize_qweather_warning_shapes(self):
        v7 = {
            "warning": [
                {
                    "id": "1",
                    "title": "雷电橙色预警",
                    "typeName": "雷电",
                    "severityColor": "Orange",
                    "text": "可能发生雷电活动",
                }
            ]
        }
        v1 = {
            "alerts": [
                {
                    "identifier": "2",
                    "headline": "暴雨红色预警",
                    "eventType": "暴雨",
                    "color": {"code": "red"},
                    "description": "强降水持续",
                }
            ]
        }

        self.assertEqual("橙色", normalize_warnings(v7)[0]["color"])
        self.assertEqual("暴雨", normalize_warnings(v1)[0]["typeName"])
        self.assertEqual(4, normalize_warnings(v1)[0]["levelScore"])


if __name__ == "__main__":
    unittest.main()
