import asyncio
import argparse
import io
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from . import cache
from .config import SITES
from .logging_config import configure_logging
from .scheduler import ScheduledJobRunner, next_complete_hour, run_daemon


if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


TIMEZONE = ZoneInfo("Asia/Shanghai")


def _locations():
    return [
        {
            "name": room["name"],
            "lon": room["lon"],
            "lat": room["lat"],
            "county": room["county"],
        }
        for room in SITES
    ]


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(prog="weather-analysis")
    parser.add_argument("--clear-cache", action="store_true", help="清除本地天气缓存")
    subparsers = parser.add_subparsers(dest="command")
    daemon = subparsers.add_parser("daemon", help="启动常驻定时任务")
    daemon.add_argument("--no-immediate", action="store_true", help="启动后不立即执行整点风险检查")
    hourly = subparsers.add_parser("hourly", help="执行一次整点风险检查")
    hourly.add_argument("--at", help="目标整点，ISO 8601 格式")
    return parser.parse_args(argv)


def _hourly_target(value: str | None) -> datetime:
    if not value:
        return next_complete_hour()
    target = datetime.fromisoformat(value)
    if target.tzinfo is None:
        target = target.replace(tzinfo=TIMEZONE)
    return target.astimezone(TIMEZONE).replace(minute=0, second=0, microsecond=0)


async def main(argv=None):
    args = _parse_args(argv)
    logger = configure_logging(console=args.command == "daemon")
    if args.clear_cache:
        cache.clear()
        logger.info("缓存已清除")
        print("缓存已清除。")
        return 0

    locations = _locations()
    if args.command == "daemon":
        try:
            await run_daemon(ScheduledJobRunner(locations), immediate=not args.no_immediate)
        except RuntimeError as error:
            logger.error("无法启动守护进程: %s", error)
            print(f"无法启动守护进程: {error}", file=sys.stderr)
            return 2
        return 0
    if args.command == "hourly":
        run_result = await ScheduledJobRunner(locations).run_hourly_risk(_hourly_target(args.at))
        if run_result is None:
            return 2
        result, report_path = run_result
        if report_path:
            print(report_path.read_text(encoding="utf-8"), end="")
        else:
            print("下一小时及未来3小时暂无橙色、红色或官方预警机房。")
        return 2 if result.get("total", 0) and result.get("failed", 0) >= result["total"] else 0

    run_result = await ScheduledJobRunner(locations).run_full_forecast()
    if run_result is None:
        return 2
    weather_data, report = run_result
    print(report)
    if weather_data.get("total", 0) and weather_data.get("failed", 0) >= weather_data["total"]:
        return 2
    return 0


def run():
    try:
        exit_code = asyncio.run(main())
    except KeyboardInterrupt:
        configure_logging().info("收到停止信号")
        exit_code = 0
    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    run()
