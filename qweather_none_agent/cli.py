import asyncio
import io
import sys

from . import cache
from .config import SITES
from .report import ReportGenerator
from .weather import WeatherTool


if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


async def main():
    if "--clear-cache" in sys.argv:
        cache.clear()
        print("缓存已清除。")
        return 0

    locations = [
        {
            "name": r["name"],
            "lon": r["lon"],
            "lat": r["lat"],
            "county": r["county"],
        }
        for r in SITES
    ]

    weather_data = await WeatherTool.run(locations)

    generator = ReportGenerator(locations, region="示例区域")
    report = generator.generate(weather_data)
    print(report)
    if weather_data.get("total", 0) and weather_data.get("failed", 0) >= weather_data["total"]:
        return 2
    return 0


def run():
    exit_code = asyncio.run(main())
    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    run()
