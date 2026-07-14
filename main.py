
import asyncio
import sys
import io

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from config import SITES
from tools.weather import WeatherTool
from report import ReportGenerator
import cache


async def main():
    if "--clear-cache" in sys.argv:
        cache.clear()
        print("缓存已清除。")
        return

    locations = [
        {"name": r["name"],
         "lon": r["lon"],
         "lat": r["lat"],
         "county": r["county"]
         } for r in SITES]

    print("=" * 60)
    print(f"  示例区域机房施工天气评估")
    print("=" * 60)
    print(f"  覆盖机房: {len(locations)} 个")
    print()

    weather_data = await WeatherTool.run(locations)

    generator = ReportGenerator(locations, region="示例区域")
    report = generator.generate(weather_data)
    print(report)


if __name__ == "__main__":
    asyncio.run(main())
