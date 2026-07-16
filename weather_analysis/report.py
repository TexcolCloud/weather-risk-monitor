from collections import defaultdict

from .aggregation import (
    CountyAggregator,
    dedupe_warnings,
    find_rain_dates,
    find_temp_dates,
    find_weather_dates,
    room_with_extreme,
    to_number,
)
from .selectors import select_top_rooms
from .warning_rules import (
    evaluate_forecast_hazards,
    forecast_report_level,
    is_forecast_alert,
)


def _fmt_date(date_str):
    if not date_str:
        return ""
    parts = date_str.split("-")
    if len(parts) == 3:
        return f"{int(parts[1])}月{int(parts[2])}日"
    return date_str


def _fmt_date_range(dates):
    if not dates:
        return ""
    if len(dates) == 1:
        return _fmt_date(dates[0])
    first = _fmt_date(dates[0])
    last = _fmt_date(dates[-1])
    first_m, *_ = first.split("月")
    if first_m and last.startswith(first_m + "月"):
        last = last[len(first_m) + 1 :]
    return f"{first}至{last}"


def _compact_warning_title(title):
    text = (title or "").strip()
    for marker in ("发布", "解除"):
        text = text.replace(marker, "")
    return text


class ReportGenerator:
    def __init__(self, locations, region="示例区域"):
        self.locations = locations
        self.region = region
        self._aggregator = CountyAggregator(locations)

    def _get_overall_level(self, warned_counties):
        return forecast_report_level(warned_counties)

    def _hazard_type(self, c):
        return [(h["name"], h["level"]) for h in evaluate_forecast_hazards(c)]

    def _hazard_label(self, c, max_items=2):
        labels = []
        for hazard, _ in self._hazard_type(c):
            if hazard not in labels:
                labels.append(hazard)

        if len(labels) > 1 and "官方预警" in labels:
            labels.remove("官方预警")

        if c.get("maxRainHours", 0) >= 3 and "连续降雨" not in labels:
            rain_index = next(
                (i for i, label in enumerate(labels) if label in ("暴雨", "强降水")),
                None,
            )
            insert_at = rain_index + 1 if rain_index is not None else len(labels)
            labels.insert(insert_at, "连续降雨")

        if not labels:
            return "一般关注"
        return "、".join(labels[:max_items])

    def _is_significant_risk(self, c):
        return is_forecast_alert(c)

    def _format_county_risk(self, c, is_highest=False):
        name = c["name"]
        warned = c["warnedCount"]
        total = c["roomCount"]
        temp = to_number(c.get("maxTemp"))
        min_temp = to_number(c.get("minTemp"), None)
        rain_hours = to_number(c.get("maxRainHours"))
        max_wind = to_number(c.get("maxWind"))
        max_precip = to_number(c.get("maxPrecip"))
        has_thunder = c.get("hasThunder", False)
        has_fog = c.get("hasFogHaze", False)
        official_title = c.get("officialWarningTitle", "")
        official_level = c.get("officialWarningLevel", "")

        hazard_types = self._hazard_type(c)
        if not hazard_types:
            return f"* {name}：涉及{warned}/{total}个机房。"
        primary_hazard, primary_level = hazard_types[0]

        prefix = f"* {name}："
        desc_parts = []
        temp_added = False

        def append_high_temp():
            nonlocal temp_added
            if temp_added:
                return
            temp_added = True
            if temp >= 40:
                high_dates = find_temp_dates(c, 40, high=True)
                cont = c.get("maxCont40", 0)
                date_str = _fmt_date_range(high_dates)
                if date_str:
                    desc_parts.append(f"{date_str}最高{temp}℃")
                else:
                    desc_parts.append(f"最高{temp}℃")
                if cont > 0:
                    desc_parts.append(f"40℃以上持续约{cont}小时")
            elif temp >= 37:
                desc_parts.append(f"最高{temp}℃")
                cont = c.get("maxCont38", 0) if temp >= 38 else c.get("maxCont37", 0)
                cont_label = "38℃以上" if temp >= 38 else "37℃以上"
                if cont > 0:
                    desc_parts.append(f"{cont_label}持续约{cont}小时")
            elif to_number(c.get("maxContDaily35")) >= 3:
                dates = find_temp_dates(c, 35, high=True)
                date_str = _fmt_date_range(dates)
                desc_parts.append(f"{date_str}连续高温" if date_str else "连续高温")

        if is_highest:
            desc_parts.append("风险最高")

        if warned == total and total > 1:
            desc_parts.append(f"{total}个机房全部纳入预警")
        else:
            desc_parts.append(f"涉及{warned}/{total}个机房")

        if primary_hazard in ("红色高温", "橙色高温", "高温"):
            append_high_temp()

        elif primary_hazard in ("低温结冰", "道路结冰", "低温"):
            if min_temp is not None:
                desc_parts.append(f"最低{min_temp}℃")
            else:
                desc_parts.append("需注意道路结冰")
            cont = to_number(c.get("maxContBelow0"))
            if cont > 0:
                desc_parts.append(f"0℃以下持续约{cont}小时")

        elif primary_hazard in ("冰雹",):
            dates = find_weather_dates(c, ("冰雹",))
            date_str = _fmt_date_range(dates)
            if date_str:
                desc_parts.append(f"{date_str}将出现冰雹")
            else:
                desc_parts.append("将出现冰雹天气")

        elif primary_hazard in ("冻雨",):
            dates = find_weather_dates(c, ("冻雨", "冰粒"))
            date_str = _fmt_date_range(dates)
            if date_str:
                desc_parts.append(f"{date_str}将出现冻雨")
            else:
                desc_parts.append("将出现冻雨天气")

        elif primary_hazard in ("暴雪", "降雪"):
            dates = find_weather_dates(c, ("雪",))
            date_str = _fmt_date_range(dates)
            if date_str:
                desc_parts.append(f"{date_str}将出现{primary_hazard}")
            else:
                desc_parts.append(f"将出现{primary_hazard}天气")

        elif primary_hazard in ("红色大风", "橙色大风", "大风", "强风"):
            desc_parts.append(f"最大风力{max_wind}级")

        elif primary_hazard in ("暴雨", "强降水"):
            desc_parts.append("有短时强降雨")

        elif primary_hazard in ("雷暴",):
            if has_thunder:
                desc_parts.append("将出现雷暴天气")

        elif primary_hazard in ("雾霾",):
            if has_fog:
                desc_parts.append("将出现雾霾天气")

        if not temp_added and (
            any(ht in ("红色高温", "橙色高温", "高温") for ht, _ in hazard_types)
            or temp >= 37
            or to_number(c.get("maxContDaily35")) >= 3
        ):
            append_high_temp()

        for ht, level in hazard_types[1:]:
            if ht in ("红色高温", "橙色高温", "高温"):
                continue
            if ht in ("低温结冰", "道路结冰", "低温") and primary_hazard in (
                "低温结冰",
                "道路结冰",
                "低温",
            ):
                continue
            if ht in ("冰雹", "冻雨", "暴雪", "降雪"):
                continue
            if ht in ("红色大风", "橙色大风", "大风", "强风"):
                desc_parts.append(f"最大风力{max_wind}级")
                continue
            if ht in ("暴雨", "强降水") and max_precip > 0:
                desc_parts.append("伴有短时强降雨")
                continue
            if ht in ("雷暴",) and has_thunder:
                desc_parts.append("伴有雷暴")
                continue
            if ht in ("雾霾",) and has_fog:
                desc_parts.append("有雾霾天气")
                continue

        if rain_hours > 0:
            desc_parts.append("伴有连续降雨")
        if (
            max_precip >= 8
            and primary_hazard not in ("暴雨", "强降水")
            and not any("短时强降雨" in part for part in desc_parts)
        ):
            desc_parts.append("伴有短时强降雨")
        if has_thunder and "伴有雷暴" not in desc_parts:
            desc_parts.append("伴有雷暴")
        if (
            max_wind >= 6
            and primary_hazard not in ("红色大风", "橙色大风", "大风", "强风")
            and not any(part.startswith("最大风力") for part in desc_parts)
        ):
            desc_parts.append(f"最大风力{max_wind}级")
        if has_fog and "有雾霾天气" not in desc_parts:
            desc_parts.append("有雾霾天气")
        compact_title = _compact_warning_title(official_title)
        if compact_title and (official_level == "红色" or "红色" in compact_title):
            desc_parts.append(compact_title)

        return prefix + "，".join(desc_parts) + "。"

    def _generate_timeline(self, warned_counties, highest_name=None):
        entries = []

        hail = [c for c in warned_counties if c["hasHail"]]
        if hail:
            c = hail[0]
            dates = find_weather_dates(c, ("冰雹",))
            if dates:
                entries.append(
                    f"{_fmt_date_range(dates)}：{c['name']}将出现冰雹天气，为本轮最高风险事件。"
                )

        freezing = [c for c in warned_counties if c["hasFreezing"]]
        if freezing and not hail:
            c = freezing[0]
            dates = find_weather_dates(c, ("冻雨", "冰粒"))
            if dates:
                entries.append(
                    f"{_fmt_date_range(dates)}：{c['name']}将出现冻雨天气，"
                    f"路面可能结冰，为重点关注区域。"
                )

        snow = [c for c in warned_counties if c["hasSnow"]]
        if snow and not hail and not freezing:
            c = snow[0]
            dates = find_weather_dates(c, ("雪",))
            label = "暴雪" if c["maxContBelow0"] >= 6 else "降雪"
            if dates:
                min_temp = to_number(c.get("minTemp"), None)
                min_text = f"，最低{min_temp}℃" if min_temp is not None else ""
                entries.append(
                    f"{_fmt_date_range(dates)}：{c['name']}将出现{label}天气，"
                    f"需注意道路湿滑和机房渗漏{min_text}。"
                )

        seen_temp = set()
        temp_added = 0

        highest = next((c for c in warned_counties if c["name"] == highest_name), None)
        if (
            highest
            and to_number(highest.get("maxTemp")) >= 37
            and to_number(highest.get("maxCont37")) >= 3
        ):
            seen_temp.add(highest["name"])
            temp_added += 1
            dates = find_temp_dates(highest, 37, high=True)
            if dates:
                t = highest["maxTemp"]
                entries.append(
                    f"{_fmt_date_range(dates)}：{highest['name']}为本轮最高风险区域，"
                    f"将出现连续{t}℃高温，37℃以上最长持续{highest['maxCont37']}小时。"
                )

        for c in warned_counties:
            name = c["name"]
            temp = to_number(c.get("maxTemp"))
            if temp >= 40 and name not in seen_temp:
                seen_temp.add(name)
                temp_added += 1
                dates = find_temp_dates(c, 40, high=True)
                if dates:
                    entries.append(
                        f"{_fmt_date_range(dates)}：{name}连续出现{temp}℃红色高温，最高风险区域。"
                    )
            elif temp >= 37 and temp_added < 2 and c["maxCont37"] >= 3 and name not in seen_temp:
                seen_temp.add(name)
                temp_added += 1
                dates = find_temp_dates(c, 37, high=True)
                if dates:
                    entries.append(
                        f"{_fmt_date_range(dates)}：{name}将出现连续{temp}℃高温，"
                        f"37℃以上最长持续{c['maxCont37']}小时。"
                    )

        cold = [
            c
            for c in warned_counties
            if to_number(c.get("maxContBelow0")) >= 3 and not snow and not freezing
        ]
        for c in cold[:1]:
            dates = find_temp_dates(c, 0, high=False)
            if dates:
                entries.append(
                    f"{_fmt_date_range(dates)}：{c['name']}将出现持续低温天气，"
                    f"最低{c['minTemp']}℃，0℃以下最长持续{c['maxContBelow0']}小时。"
                )

        wind = [c for c in warned_counties if to_number(c.get("maxWind")) >= 8]
        for c in wind[:1]:
            entries.append(f"{c['name']}最大风力{c['maxWind']}级，需注意高空作业安全。")

        heavy_rain = sorted(
            [c for c in warned_counties if to_number(c.get("maxPrecip")) >= 8],
            key=lambda c: to_number(c.get("maxPrecip")),
            reverse=True,
        )
        for c in heavy_rain[:1]:
            entries.append(f"{c['name']}最大小时降水{c['maxPrecip']}mm，需关注山洪和地质灾害风险。")

        rain_counties = sorted(
            [c for c in warned_counties if to_number(c.get("maxRainHours")) >= 3],
            key=lambda c: to_number(c.get("maxRainHours")),
            reverse=True,
        )
        for c in rain_counties[:2]:
            name = c["name"]
            rain_hours = c["maxRainHours"]
            rain_dates = find_rain_dates(c)
            if rain_dates:
                entries.append(
                    f"{_fmt_date_range(rain_dates)}：{name}将出现连续降雨过程，"
                    f"最长连续降雨{rain_hours}小时。"
                )

        return entries

    def _generate_reminder(self, warned_counties):
        if not warned_counties:
            return f"{self.region}综合服务支撑中心提醒：未来168小时天气状况良好，适宜开展各项作业。"

        top_names = [c["name"] for c in warned_counties[:4]]
        names_str = "、".join(top_names)

        hazards_global = set()
        for c in warned_counties:
            for ht, _ in self._hazard_type(c):
                hazards_global.add(ht)

        parts = []
        if "红色高温" in hazards_global or "橙色高温" in hazards_global or "高温" in hazards_global:
            parts.append("避开高温时段作业")
        if "暴雨" in hazards_global or "强降水" in hazards_global:
            parts.append("关注山洪和内涝风险")
        if (
            "红色大风" in hazards_global
            or "橙色大风" in hazards_global
            or "大风" in hazards_global
            or "强风" in hazards_global
        ):
            parts.append("注意高空作业安全")
        if "冰雹" in hazards_global:
            parts.append("冰雹期间停止户外作业")
        if (
            "冻雨" in hazards_global
            or "低温结冰" in hazards_global
            or "道路结冰" in hazards_global
            or "低温" in hazards_global
        ):
            parts.append("注意道路结冰和防寒保暖")
        if "暴雪" in hazards_global or "降雪" in hazards_global:
            parts.append("及时清理屋顶积雪，防止机房渗漏")
        if "雷暴" in hazards_global:
            parts.append("雷暴期间停止户外及高空作业")
        if "雾霾" in hazards_global:
            parts.append("雾霾天气注意交通安全")

        if not parts:
            parts.append("密切关注天气变化")

        attention = "、".join(parts)
        return (
            f"{self.region}综合服务支撑中心提醒："
            f"请重点关注{names_str}等区域装维与综维安全生产情况，"
            f"{attention}。"
        )

    def _room_focus_period(self, room):
        parts = []
        daily = room.get("dailySummary", [])
        if to_number(room.get("tmax")) >= 40:
            dates = [
                d["date"]
                for d in daily
                if to_number(d.get("tmax"), None) is not None and to_number(d.get("tmax")) >= 40
            ]
            date_text = _fmt_date_range(dates)
            parts.append(f"{date_text}高温" if date_text else "高温")
        elif to_number(room.get("tmax")) >= 37:
            dates = [
                d["date"]
                for d in daily
                if to_number(d.get("tmax"), None) is not None and to_number(d.get("tmax")) >= 37
            ]
            date_text = _fmt_date_range(dates)
            parts.append(f"{date_text}高温" if date_text else "高温")
        elif to_number(room.get("maxContDaily35")) >= 3:
            dates = [
                d["date"]
                for d in daily
                if to_number(d.get("tmax"), None) is not None and to_number(d.get("tmax")) >= 35
            ]
            date_text = _fmt_date_range(dates)
            parts.append(f"{date_text}连续高温" if date_text else "连续高温")

        if to_number(room.get("maxRainHours")) >= 3:
            dates = [d["date"] for d in daily if to_number(d.get("precip")) > 0]
            date_text = _fmt_date_range(dates)
            parts.append(f"{date_text}连续降雨" if date_text else "连续降雨")
        elif to_number(room.get("maxPrecip")) >= 8:
            dates = [d["date"] for d in daily if to_number(d.get("precip")) > 0]
            date_text = _fmt_date_range(dates)
            parts.append(f"{date_text}短时强降雨" if date_text else "短时强降雨")

        weather_parts = []
        if room.get("hasThunder"):
            weather_parts.append("雷暴")
        if room.get("hasHail"):
            weather_parts.append("冰雹")
        if room.get("hasFreezing"):
            weather_parts.append("冻雨")
        if room.get("hasSnow"):
            weather_parts.append("降雪")
        if room.get("hasFog") or room.get("hasHaze") or room.get("hasSand"):
            weather_parts.append("雾霾")
        if weather_parts:
            dates = [
                d["date"]
                for d in daily
                if any(
                    kw in d.get("textDay", "") + d.get("textNight", "")
                    for kw in ("雷", "冰雹", "冻雨", "冰粒", "雪", "雾", "霾", "沙")
                )
            ]
            date_text = _fmt_date_range(dates)
            label = "、".join(weather_parts)
            parts.append(f"{date_text}{label}" if date_text else label)

        if parts:
            return "；".join(parts[:2])

        warnings = room.get("officialWarnings") or []
        if warnings:
            warning = warnings[0]
            pub_time = str(warning.get("pubTime") or "")
            date_text = _fmt_date(pub_time[:10]) if len(pub_time) >= 10 else ""
            hazard = warning.get("typeName") or "天气"
            return f"{date_text}{hazard}预警" if date_text else f"{hazard}预警"
        return "重点风险时段待小时预报补充"

    def generate(self, weather_data):
        rooms_data = weather_data.get("counties", [])
        update_time = weather_data.get("updateTime", "")
        total = weather_data.get("total", len(self.locations))
        failed = weather_data.get("failed", 0)
        partial_failed = weather_data.get("partialFailed", 0)
        warning_failed = weather_data.get("warningFailed", 0)
        auxiliary_warnings = weather_data.get("auxiliaryWarnings", [])
        official_suggestions = weather_data.get("officialSuggestions", [])

        today_str = ""
        if update_time:
            try:
                date_part = update_time.split("T")[0]
                today_str = _fmt_date(date_part)
            except Exception:
                pass

        county_stats = self._aggregator.aggregate(rooms_data)
        warned_counties = [c for c in county_stats if c["warnedCount"] > 0]
        affected_count = sum(
            1
            for room in rooms_data
            if is_forecast_alert(
                {
                    "maxTemp": room.get("tmax", 0),
                    "minTemp": room.get("tmin", 0),
                    "maxWind": room.get("maxWind", 0),
                    "maxPrecip": room.get("maxPrecip", 0),
                    "maxDailyPrecip": room.get("maxDailyPrecip", 0),
                    "maxPrecip3h": room.get("maxPrecip3h", 0),
                    "maxPrecip6h": room.get("maxPrecip6h", 0),
                    "maxPrecip12h": room.get("maxPrecip12h", 0),
                    "maxPrecip24h": room.get("maxPrecip24h", 0),
                    "maxContDaily35": room.get("maxContDaily35", 0),
                    "hasHail": room.get("hasHail", False),
                    "hasFreezing": room.get("hasFreezing", False),
                    "hasSnow": room.get("hasSnow", False),
                    "hasThunder": room.get("hasThunder", False),
                    "hasFogHaze": room.get("hasFog", False)
                    or room.get("hasHaze", False)
                    or room.get("hasSand", False),
                    "officialWarnings": room.get("officialWarnings", []),
                }
            )
        )
        overall_level = self._get_overall_level(warned_counties)
        high_risk = [c for c in warned_counties if self._is_significant_risk(c)]
        focus_counties = high_risk or warned_counties

        lines = []

        lines.append(f"【{self.region}机房天气灾害预警（{today_str}）】")
        lines.append("")

        if affected_count > 0:
            if affected_count == total:
                lines.append(
                    f"未来168小时全市{total}个机房均受天气影响，"
                    f"其中{affected_count}个机房达到机房预警标准，"
                    f"综合等级为{overall_level}。"
                )
            else:
                lines.append(
                    f"未来168小时全市{total}个机房中有{affected_count}个达到机房预警标准，"
                    f"综合等级为{overall_level}。"
                )
        else:
            if failed:
                lines.append(
                    f"未来168小时全市{total}个机房暂未识别到机房预警，"
                    f"但有{failed}个机房天气数据获取失败，需补充核查。"
                )
            else:
                lines.append(f"未来168小时全市{total}个机房暂无机房预警。")
        if failed:
            lines.append(
                f"数据提示：{failed}个机房168小时预报数据获取失败，相关风险未按官方预警单独判定。"
            )
        if auxiliary_warnings:
            summaries = []
            for item in auxiliary_warnings[:3]:
                warning = next(iter(item.get("warnings", [])), None)
                if isinstance(warning, dict) and warning.get("title"):
                    summaries.append(
                        f"{item.get('county', '未分区')}：{_compact_warning_title(warning['title'])}"
                    )
            if summaries:
                lines.append(f"辅助核查：预报数据缺失区域存在官方预警，{'；'.join(summaries)}。")
        if partial_failed:
            lines.append(
                f"数据提示：{partial_failed}个机房小时级天气数据缺失或不连续，"
                "连续高温、连续降雨和小时降水判断可能不完整。"
            )
        if warning_failed:
            lines.append(
                f"数据提示：{warning_failed}个机房未取得官方预警数据，已按天气预报结果判断。"
            )
        if official_suggestions:
            summaries = []
            for item in official_suggestions[:3]:
                warning = next(iter(item.get("warnings", [])), None)
                if isinstance(warning, dict) and warning.get("title"):
                    summaries.append(
                        f"{item.get('county', '未分区')}：{_compact_warning_title(warning['title'])}"
                    )
            if summaries:
                lines.append(f"官方预警建议（不参与等级）：{'；'.join(summaries)}。")
        lines.append("")

        if warned_counties:
            lines.append("一、重点风险")
            lines.append("")

            for idx, c in enumerate(focus_counties[:4]):
                lines.append(self._format_county_risk(c, is_highest=(idx == 0)))
            lines.append("")

            lines.append("二、重点机房")
            lines.append("")
            top_rooms = select_top_rooms(rooms_data, focus_counties)

            by_cty = defaultdict(list)
            order = []
            for r in top_rooms:
                ct = r.get("county", "")
                if ct not in by_cty:
                    order.append(ct)
                by_cty[ct].append(r)

            for idx, ct in enumerate(order):
                rooms = by_cty[ct]
                has_fog = any(r.get("hasFog") for r in rooms)
                has_haze = any(r.get("hasHaze") for r in rooms)
                has_sand = any(r.get("hasSand") for r in rooms)
                official_warnings = []
                for r in rooms:
                    official_warnings.extend(r.get("officialWarnings", []))
                official_warnings = dedupe_warnings(official_warnings)
                max_temp_source = room_with_extreme(rooms, "tmax")
                min_temp_source = room_with_extreme(rooms, "tmin", highest=False)
                room_stats = {
                    "maxTemp": max_temp_source.get("tmax") if max_temp_source else None,
                    "minTemp": min_temp_source.get("tmin") if min_temp_source else None,
                    "maxWind": max(to_number(r.get("maxWind")) for r in rooms),
                    "maxPrecip": max(to_number(r.get("maxPrecip")) for r in rooms),
                    "maxCont37": max(to_number(r.get("maxCont37")) for r in rooms),
                    "maxCont38": max(to_number(r.get("maxCont38")) for r in rooms),
                    "maxCont40": max(to_number(r.get("maxCont40")) for r in rooms),
                    "maxContDaily35": max(to_number(r.get("maxContDaily35")) for r in rooms),
                    "maxContBelow0": max(to_number(r.get("maxContBelow0")) for r in rooms),
                    "maxRainHours": max(to_number(r.get("maxRainHours")) for r in rooms),
                    "maxDailyPrecip": max(to_number(r.get("maxDailyPrecip")) for r in rooms),
                    "maxPrecip3h": max(to_number(r.get("maxPrecip3h")) for r in rooms),
                    "maxPrecip6h": max(to_number(r.get("maxPrecip6h")) for r in rooms),
                    "maxPrecip12h": max(to_number(r.get("maxPrecip12h")) for r in rooms),
                    "maxPrecip24h": max(to_number(r.get("maxPrecip24h")) for r in rooms),
                    "hasHail": any(r.get("hasHail") for r in rooms),
                    "hasFreezing": any(r.get("hasFreezing") for r in rooms),
                    "hasSnow": any(r.get("hasSnow") for r in rooms),
                    "hasThunder": any(r.get("hasThunder") for r in rooms),
                    "hasFogHaze": has_fog or has_haze or has_sand,
                    "officialWarnings": official_warnings[:5],
                }
                label = self._hazard_label(room_stats)
                lines.append(f"{idx + 1}. {ct}（{label}）")
                for r in rooms:
                    lines.append(f"    * {r['name']}：{self._room_focus_period(r)}")
                lines.append("")

            lines.append("三、关注过程")
            lines.append("")
            timeline = self._generate_timeline(
                focus_counties, focus_counties[0]["name"] if focus_counties else None
            )
            for entry in timeline[:2]:
                lines.append(f"* {entry}")
            lines.append("")

        if not focus_counties and (failed or partial_failed):
            lines.append(
                f"{self.region}综合服务支撑中心提醒：部分机房天气数据获取不完整，"
                "请补充核查后再安排对天气敏感的作业。"
            )
        else:
            lines.append(self._generate_reminder(focus_counties))

        return "\n".join(lines)
