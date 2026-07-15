"""Async client and response normalization for QWeather APIs."""

import asyncio
import logging
import os
import random
from types import TracebackType

import httpx

from . import cache
from .models import OfficialWarning, Room


logger = logging.getLogger(__name__)

MAX_CONCURRENT = 50
MAX_REQUESTS_PER_SECOND = int(os.environ.get("WEATHER_ANALYSIS_MAX_REQUESTS_PER_SECOND", "10"))
MAX_RETRIES = 3
BACKOFF_BASE = 2.0
BACKOFF_MAX_EXPONENT = 8

WARNING_COLOR_LEVELS = {
    "white": 0,
    "blue": 1,
    "green": 1,
    "yellow": 2,
    "orange": 3,
    "red": 4,
    "白色": 0,
    "蓝色": 1,
    "绿色": 1,
    "黄色": 2,
    "橙色": 3,
    "红色": 4,
}


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _backoff_delay(attempt):
    attempt = min(attempt, BACKOFF_MAX_EXPONENT)
    base = BACKOFF_BASE**attempt
    jitter = random.randint(0, (2**attempt) - 1) if attempt > 0 else 0
    return base + jitter


def _warning_color(raw):
    if isinstance(raw, dict):
        raw = raw.get("code") or raw.get("name") or raw.get("color")
    color = str(raw or "").strip().lower()
    if color.isdigit():
        return {1: "蓝色", 2: "黄色", 3: "橙色", 4: "红色"}.get(int(color), "")
    mapping = {
        "blue": "蓝色",
        "green": "蓝色",
        "yellow": "黄色",
        "orange": "橙色",
        "red": "红色",
        "白色": "白色",
        "蓝色": "蓝色",
        "绿色": "蓝色",
        "黄色": "黄色",
        "橙色": "橙色",
        "红色": "红色",
    }
    return mapping.get(color, str(raw or "").strip())


def _warning_level(color):
    return WARNING_COLOR_LEVELS.get(str(color or "").strip().lower(), 0)


def normalize_warnings(data) -> list[OfficialWarning]:
    if not isinstance(data, dict):
        return []
    raw_warnings = data.get("warning")
    if raw_warnings is None:
        raw_warnings = data.get("alerts")
    if not isinstance(raw_warnings, list):
        return []

    warnings: list[OfficialWarning] = []
    for item in raw_warnings:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").lower()
        if status in {"cancel", "cancelled", "解除", "已解除"}:
            continue
        color = _warning_color(
            item.get("severityColor")
            or item.get("color")
            or item.get("severity")
            or item.get("level")
        )
        warnings.append(
            {
                "id": item.get("id") or item.get("identifier") or "",
                "title": item.get("title") or item.get("headline") or "",
                "typeName": item.get("typeName") or item.get("eventType") or item.get("type") or "",
                "level": item.get("level") or item.get("severity") or "",
                "color": color,
                "levelScore": _warning_level(color),
                "text": item.get("text")
                or item.get("description")
                or item.get("instruction")
                or "",
                "sender": item.get("sender") or item.get("senderName") or "",
                "pubTime": item.get("pubTime") or item.get("sent") or item.get("effective") or "",
            }
        )
    warnings.sort(key=lambda warning: warning["levelScore"], reverse=True)
    return warnings


class QWeatherClient:
    def __init__(
        self,
        api_key: str,
        max_concurrent: int = MAX_CONCURRENT,
        max_requests_per_second: int = MAX_REQUESTS_PER_SECOND,
    ):
        if max_requests_per_second < 1:
            raise ValueError("max_requests_per_second must be positive")
        self._headers = {"X-QW-API-KEY": api_key}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._rate_lock = asyncio.Lock()
        self._request_interval = 1 / max_requests_per_second
        self._next_request_at = 0.0
        self._limits = httpx.Limits(
            max_connections=max_concurrent,
            max_keepalive_connections=20,
        )
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(headers=self._headers, limits=self._limits)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ):
        if self._client is not None:
            await self._client.aclose()

    @staticmethod
    def location(room: Room) -> str:
        lat = _safe_float(room.get("lat"), 0.0)
        lon = _safe_float(room.get("lon"), 0.0)
        return f"{lon:.2f},{lat:.2f}"

    async def _wait_for_request_slot(self) -> None:
        loop = asyncio.get_running_loop()
        async with self._rate_lock:
            now = loop.time()
            scheduled = max(now, self._next_request_at)
            self._next_request_at = scheduled + self._request_interval
        delay = scheduled - loop.time()
        if delay > 0:
            await asyncio.sleep(delay)

    async def fetch(self, url, params, lat, lon, endpoint, ttl, force_refresh=False):
        if not force_refresh:
            cached = cache.get(lat, lon, endpoint, ttl)
            if cached is not None:
                return cached
        if self._client is None:
            raise RuntimeError("QWeatherClient must be used as an async context manager")

        consecutive = 0
        for _ in range(MAX_RETRIES):
            delay = None
            try:
                async with self._semaphore:
                    await self._wait_for_request_slot()
                    response = await self._client.get(url, params=params, timeout=10)
                status = response.status_code
                if status == 429:
                    consecutive += 1
                    delay = _backoff_delay(consecutive)
                elif status in {400, 403}:
                    logger.warning("天气接口拒绝请求: endpoint=%s status=%s", endpoint, status)
                    return None
                elif status == 200:
                    data = response.json()
                    if isinstance(data, dict) and data.get("code") == "200":
                        cache.set(lat, lon, endpoint, data)
                        return data
                    consecutive += 1
                    delay = _backoff_delay(consecutive)
                elif status >= 500:
                    consecutive += 1
                    delay = _backoff_delay(consecutive)
                else:
                    logger.warning("天气接口返回异常状态: endpoint=%s status=%s", endpoint, status)
                    return None
            except httpx.TimeoutException:
                consecutive += 1
                delay = _backoff_delay(consecutive)
            except Exception:
                logger.exception("天气接口请求异常: endpoint=%s", endpoint)
                consecutive += 1
                delay = _backoff_delay(consecutive)

            if delay is not None:
                await asyncio.sleep(delay)
        return None
