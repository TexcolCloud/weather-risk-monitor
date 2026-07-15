import unittest
from unittest.mock import AsyncMock, Mock, patch

from weather_analysis.qweather_client import QWeatherClient, normalize_warnings


class QWeatherClientTest(unittest.TestCase):
    def test_api_key_is_required(self):
        with self.assertRaisesRegex(ValueError, "QWEATHER_API_KEY"):
            QWeatherClient("")

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


class QWeatherClientAsyncTest(unittest.IsolatedAsyncioTestCase):
    async def test_force_refresh_bypasses_cached_payload(self):
        response = Mock(status_code=200)
        response.json.return_value = {"code": "200", "hourly": []}
        client = QWeatherClient("test-key")
        client._client = AsyncMock()
        client._client.get.return_value = response

        with (
            patch("weather_analysis.qweather_client.cache.get") as cache_get,
            patch("weather_analysis.qweather_client.cache.set") as cache_set,
            patch.object(client, "_wait_for_request_slot", new=AsyncMock()),
        ):
            result = await client.fetch(
                "https://example.invalid",
                {},
                30.0,
                111.0,
                "168h",
                60,
                force_refresh=True,
            )

        cache_get.assert_not_called()
        cache_set.assert_called_once()
        self.assertEqual("200", result["code"])


if __name__ == "__main__":
    unittest.main()
