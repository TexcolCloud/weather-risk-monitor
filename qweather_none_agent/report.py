
from collections import defaultdict

from .standards import evaluate_hazards, is_significant, report_level, risk_score


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
        last = last[len(first_m) + 1:]
    return f"{first}至{last}"


class ReportGenerator:

    def __init__(self, locations, region="示例区域"):
        self.locations = locations
        self.region = region
        self.county_map = {}
        self.rooms_by_county = defaultdict(list)
        for r in locations:
            ct = r.get("county", "")
            self.county_map[r["name"]] = ct
            self.rooms_by_county[ct].append(r["name"])

    def _county_stats(self, rooms_data):
        by_county = defaultdict(list)
        for rd in rooms_data:
            ct = rd.get("county", "")
            by_county[ct].append(rd)

        stats = []
        for ct, rooms in by_county.items():
            tmax_list = [r["tmax"] for r in rooms]
            tmin_list = [r["tmin"] for r in rooms]
            total_rooms = len(self.rooms_by_county.get(ct, rooms))
            stats.append({
                "name": ct,
                "roomCount": total_rooms,
                "warnedCount": len(rooms),
                "maxTemp": max(tmax_list),
                "minTemp": min(tmin_list),
                "maxCont40": max(r["maxCont40"] for r in rooms),
                "maxCont38": max(r["maxCont38"] for r in rooms),
                "maxCont37": max(r["maxCont37"] for r in rooms),
                "maxContDaily35": max(r.get("maxContDaily35", 0) for r in rooms),
                "maxContBelow0": max(r["maxContBelow0"] for r in rooms),
                "hoursAbove37": max(r["hoursAbove37"] for r in rooms),
                "hoursBelow5": max(r["hoursBelow5"] for r in rooms),
                "maxPrecip": max(r["maxPrecip"] for r in rooms),
                "maxDailyPrecip": max(r.get("maxDailyPrecip", 0) for r in rooms),
                "maxPrecip3h": max(r.get("maxPrecip3h", 0) for r in rooms),
                "maxPrecip6h": max(r.get("maxPrecip6h", 0) for r in rooms),
                "maxPrecip12h": max(r.get("maxPrecip12h", 0) for r in rooms),
                "maxPrecip24h": max(r.get("maxPrecip24h", 0) for r in rooms),
                "maxRainHours": max(r["maxRainHours"] for r in rooms),
                "maxWind": max(r["maxWind"] for r in rooms),
                "hasThunder": any(r["hasThunder"] for r in rooms),
                "hasSnow": any(r["hasSnow"] for r in rooms),
                "hasFreezing": any(r["hasFreezing"] for r in rooms),
                "hasHail": any(r["hasHail"] for r in rooms),
                "hasFogHaze": any(r["hasFog"] or r["hasHaze"] or r["hasSand"] for r in rooms),
                "rooms": self.rooms_by_county.get(ct, [r["name"] for r in rooms]),
                "sampleRoom": rooms[0],
            })
        stats.sort(key=lambda x: self._rank_score(x), reverse=True)
        return stats

    def _rank_score(self, c):
        return risk_score(c)

    def _find_temp_dates(self, county_stats, threshold, high=True):
        sample = county_stats.get("sampleRoom")
        if not sample:
            return []
        dates = []
        for d in sample.get("dailySummary", []):
            if high and d["tmax"] > threshold:
                dates.append(d["date"])
            elif not high and d["tmin"] <= threshold:
                dates.append(d["date"])
        return dates

    def _find_rain_dates(self, county_stats):
        sample = county_stats.get("sampleRoom")
        if not sample:
            return []
        dates = []
        for d in sample.get("dailySummary", []):
            if float(d.get("precip", 0)) > 0:
                dates.append(d["date"])
        return dates

    def _find_weather_dates(self, county_stats, keywords):
        sample = county_stats.get("sampleRoom")
        if not sample:
            return []
        dates = []
        for d in sample.get("dailySummary", []):
            full_text = d.get("textDay", "") + d.get("textNight", "")
            if any(kw in full_text for kw in keywords):
                dates.append(d["date"])
        return dates

    def _get_overall_level(self, warned_counties):
        return report_level(warned_counties)

    def _hazard_type(self, c):
        return [(h["name"], h["level"]) for h in evaluate_hazards(c)]

    def _hazard_label(self, c, max_items=4):
        labels = []
        for hazard, _ in self._hazard_type(c):
            if hazard not in labels:
                labels.append(hazard)

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
        return is_significant(c)

    def _format_county_risk(self, c, is_highest=False):
        name = c["name"]
        warned = c["warnedCount"]
        total = c["roomCount"]
        temp = c["maxTemp"]
        min_temp = c["minTemp"]
        rain_hours = c.get("maxRainHours", 0)
        max_wind = c.get("maxWind", 0)
        max_precip = c.get("maxPrecip", 0)
        has_thunder = c.get("hasThunder", False)
        has_fog = c.get("hasFogHaze", False)

        hazard_types = self._hazard_type(c)
        if not hazard_types:
            return f"* {name}：涉及{warned}/{total}个机房。"
        primary_hazard, primary_level = hazard_types[0]

        prefix = f"* {name}："
        desc_parts = []

        if is_highest and temp < 40:
            desc_parts.append("风险最高")

        if warned == total and total > 1:
            desc_parts.append(f"{total}个机房全部纳入预警")
        else:
            desc_parts.append(f"涉及{warned}/{total}个机房")

        if primary_hazard in ("红色高温", "橙色高温", "高温"):
            if temp > 40:
                high_dates = self._find_temp_dates(c, 40, high=True)
                cont = c["maxCont40"]
                date_str = _fmt_date_range(high_dates)
                if date_str:
                    desc_parts.append(f"{date_str}将出现{temp}℃{primary_hazard}")
                else:
                    desc_parts.append(f"最高{temp}℃")
                if cont > 0:
                    desc_parts.append(f"40℃以上最长持续{cont}小时")
            else:
                desc_parts.append(f"最高{temp}℃")
                cont = c["maxCont38"] if temp > 38 else c["maxCont37"]
                cont_label = "38℃以上" if temp > 38 else "37℃以上"
                if cont > 0:
                    desc_parts.append(f"{cont_label}最长持续{cont}小时")

        elif primary_hazard in ("低温结冰", "道路结冰", "低温"):
            desc_parts.append(f"最低{min_temp}℃")
            cont = c["maxContBelow0"]
            if cont > 0:
                desc_parts.append(f"0℃以下最长持续{cont}小时")

        elif primary_hazard in ("冰雹",):
            dates = self._find_weather_dates(c, ("冰雹",))
            date_str = _fmt_date_range(dates)
            if date_str:
                desc_parts.append(f"{date_str}将出现冰雹")
            else:
                desc_parts.append("将出现冰雹天气")

        elif primary_hazard in ("冻雨",):
            dates = self._find_weather_dates(c, ("冻雨", "冰粒"))
            date_str = _fmt_date_range(dates)
            if date_str:
                desc_parts.append(f"{date_str}将出现冻雨")
            else:
                desc_parts.append("将出现冻雨天气")

        elif primary_hazard in ("暴雪", "降雪"):
            dates = self._find_weather_dates(c, ("雪",))
            date_str = _fmt_date_range(dates)
            if date_str:
                desc_parts.append(f"{date_str}将出现{primary_hazard}")
            else:
                desc_parts.append(f"将出现{primary_hazard}天气")

        elif primary_hazard in ("红色大风", "橙色大风", "大风", "强风"):
            desc_parts.append(f"最大风力{max_wind}级")

        elif primary_hazard in ("暴雨", "强降水"):
            desc_parts.append("将出现强降水过程")

        elif primary_hazard in ("雷暴",):
            if has_thunder:
                desc_parts.append("将出现雷暴天气")

        elif primary_hazard in ("雾霾",):
            if has_fog:
                desc_parts.append("将出现雾霾天气")

        for ht, level in hazard_types[1:]:
            if ht in ("红色高温", "橙色高温", "高温"):
                continue
            if ht in ("低温结冰", "道路结冰", "低温") and primary_hazard in ("低温结冰", "道路结冰", "低温"):
                continue
            if ht in ("冰雹", "冻雨", "暴雪", "降雪"):
                continue
            if ht in ("红色大风", "橙色大风", "大风", "强风"):
                desc_parts.append(f"最大风力{max_wind}级")
                continue
            if ht in ("暴雨", "强降水") and max_precip > 0:
                desc_parts.append(f"最大小时降水{max_precip:g}mm")
                continue
            if ht in ("雷暴",) and has_thunder:
                desc_parts.append("伴有雷暴")
                continue
            if ht in ("雾霾",) and has_fog:
                desc_parts.append("有雾霾天气")
                continue

        if rain_hours > 0:
            desc_parts.append("并有连续降雨过程")
        if max_precip >= 8 and primary_hazard not in ("暴雨", "强降水") and not any(
                part.startswith("最大小时降水") for part in desc_parts):
            desc_parts.append(f"最大小时降水{max_precip:g}mm")
        if has_thunder and "伴有雷暴" not in desc_parts:
            desc_parts.append("伴有雷暴")
        if max_wind >= 6 and primary_hazard not in ("红色大风", "橙色大风", "大风", "强风") and not any(
                part.startswith("最大风力") for part in desc_parts):
            desc_parts.append(f"最大风力{max_wind}级")
        if has_fog and "有雾霾天气" not in desc_parts:
            desc_parts.append("有雾霾天气")

        return prefix + "，".join(desc_parts) + "。"

    def _generate_timeline(self, warned_counties, highest_name=None):
        entries = []

        hail = [c for c in warned_counties if c["hasHail"]]
        if hail:
            c = hail[0]
            dates = self._find_weather_dates(c, ("冰雹",))
            if dates:
                entries.append(
                    f"{_fmt_date_range(dates)}：{c['name']}将出现冰雹天气，"
                    f"为本轮最高风险事件。"
                )

        freezing = [c for c in warned_counties if c["hasFreezing"]]
        if freezing and not hail:
            c = freezing[0]
            dates = self._find_weather_dates(c, ("冻雨", "冰粒"))
            if dates:
                entries.append(
                    f"{_fmt_date_range(dates)}：{c['name']}将出现冻雨天气，"
                    f"路面可能结冰，为重点关注区域。"
                )

        snow = [c for c in warned_counties if c["hasSnow"]]
        if snow and not hail and not freezing:
            c = snow[0]
            dates = self._find_weather_dates(c, ("雪",))
            label = "暴雪" if c["maxContBelow0"] >= 6 else "降雪"
            if dates:
                entries.append(
                    f"{_fmt_date_range(dates)}：{c['name']}将出现{label}天气，"
                    f"最低{c['minTemp']}℃。"
                )

        seen_temp = set()
        temp_added = 0

        highest = next((c for c in warned_counties if c["name"] == highest_name), None)
        if highest and highest["maxTemp"] > 37 and highest["maxCont37"] >= 3:
            seen_temp.add(highest["name"])
            temp_added += 1
            dates = self._find_temp_dates(highest, 37, high=True)
            if dates:
                t = highest["maxTemp"]
                entries.append(
                    f"{_fmt_date_range(dates)}：{highest['name']}为本轮最高风险区域，"
                    f"将出现连续{t}℃高温，37℃以上最长持续{highest['maxCont37']}小时。"
                )

        for c in warned_counties:
            name = c["name"]
            temp = c["maxTemp"]
            if temp > 40 and name not in seen_temp:
                seen_temp.add(name)
                temp_added += 1
                dates = self._find_temp_dates(c, 40, high=True)
                if dates:
                    entries.append(
                        f"{_fmt_date_range(dates)}：{name}连续出现{temp}℃红色高温，"
                        f"最高风险区域。"
                    )
            elif temp > 37 and temp_added < 2 and c["maxCont37"] >= 3 and name not in seen_temp:
                seen_temp.add(name)
                temp_added += 1
                dates = self._find_temp_dates(c, 37, high=True)
                if dates:
                    entries.append(
                        f"{_fmt_date_range(dates)}：{name}将出现连续{temp}℃高温，"
                        f"37℃以上最长持续{c['maxCont37']}小时。"
                    )

        cold = [c for c in warned_counties if c["maxContBelow0"] >= 3 and not snow and not freezing]
        for c in cold[:1]:
            dates = self._find_temp_dates(c, 0, high=False)
            if dates:
                entries.append(
                    f"{_fmt_date_range(dates)}：{c['name']}将出现持续低温天气，"
                    f"最低{c['minTemp']}℃，0℃以下最长持续{c['maxContBelow0']}小时。"
                )

        wind = [c for c in warned_counties if c["maxWind"] >= 8]
        for c in wind[:1]:
            entries.append(
                f"{c['name']}最大风力{c['maxWind']}级，"
                f"需注意高空作业安全。"
            )

        heavy_rain = sorted(
            [c for c in warned_counties if c.get("maxPrecip", 0) >= 8],
            key=lambda c: c["maxPrecip"], reverse=True
        )
        for c in heavy_rain[:1]:
            entries.append(
                f"{c['name']}最大小时降水{c['maxPrecip']}mm，"
                f"需关注山洪和地质灾害风险。"
            )

        rain_counties = sorted(
            [c for c in warned_counties if c.get("maxRainHours", 0) >= 3],
            key=lambda c: c["maxRainHours"], reverse=True
        )
        for c in rain_counties[:2]:
            name = c["name"]
            rain_hours = c["maxRainHours"]
            rain_dates = self._find_rain_dates(c)
            if rain_dates:
                entries.append(
                    f"{_fmt_date_range(rain_dates)}：{name}将出现连续降雨过程，"
                    f"最长连续降雨{rain_hours}小时。"
                )

        return entries

    def _generate_reminder(self, warned_counties):
        if not warned_counties:
            return f"{self.region}综合服务支撑中心提醒：未来7天天气状况良好，适宜开展各项作业。"

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
        if "红色大风" in hazards_global or "橙色大风" in hazards_global or "大风" in hazards_global or "强风" in hazards_global:
            parts.append("注意高空作业安全")
        if "冰雹" in hazards_global:
            parts.append("冰雹期间停止户外作业")
        if "冻雨" in hazards_global or "低温结冰" in hazards_global or "道路结冰" in hazards_global or "低温" in hazards_global:
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

    def _room_score(self, r):
        return risk_score(r)

    def generate(self, weather_data):
        rooms_data = weather_data.get("counties", [])
        update_time = weather_data.get("updateTime", "")
        total = weather_data.get("total", len(self.locations))
        failed = weather_data.get("failed", 0)
        partial_failed = weather_data.get("partialFailed", 0)

        today_str = ""
        if update_time:
            try:
                date_part = update_time.split("T")[0]
                today_str = _fmt_date(date_part)
            except Exception:
                pass

        county_stats = self._county_stats(rooms_data)
        warned_counties = [c for c in county_stats if c["warnedCount"] > 0]
        affected_count = sum(c["warnedCount"] for c in county_stats)
        overall_level = self._get_overall_level(warned_counties)
        high_risk = [c for c in warned_counties if self._is_significant_risk(c)]
        focus_counties = high_risk or warned_counties

        lines = []

        lines.append(f"【{self.region}机房天气灾害预警（{today_str}）】")
        lines.append("")

        if affected_count > 0:
            if affected_count == total:
                lines.append(
                    f"未来7天全市{total}个机房均受天气影响，"
                    f"其中{affected_count}个机房达到重点预警标准，"
                    f"综合等级为{overall_level}。"
                )
            else:
                lines.append(
                    f"未来7天全市{total}个机房中有{affected_count}个达到重点预警标准，"
                    f"综合等级为{overall_level}。"
                )
        else:
            if failed:
                lines.append(
                    f"未来7天全市{total}个机房暂未识别到重大天气预警，"
                    f"但有{failed}个机房天气数据获取失败，需补充核查。"
                )
            else:
                lines.append(f"未来7天全市{total}个机房暂无重大天气预警。")
        if failed:
            lines.append(f"数据提示：{failed}个机房天气数据获取失败，未纳入本次风险判断。")
        if partial_failed:
            lines.append(
                f"数据提示：{partial_failed}个机房小时级天气数据获取失败，"
                "连续高温、连续降雨和小时降水判断可能不完整。"
            )
        lines.append("")

        if warned_counties:
            lines.append("一、重点风险")
            lines.append("")

            for idx, c in enumerate(focus_counties[:6]):
                lines.append(self._format_county_risk(c, is_highest=(idx == 0)))
            lines.append("")

            lines.append("二、重点机房")
            lines.append("")
            all_rooms = sorted(rooms_data, key=lambda r: self._room_score(r), reverse=True)

            top_rooms = []
            seen_cty = defaultdict(int)
            hr_names = {c["name"] for c in focus_counties}
            for r in all_rooms:
                ct = r.get("county", "")
                if ct not in hr_names:
                    continue
                if seen_cty[ct] >= 3:
                    continue
                top_rooms.append(r)
                seen_cty[ct] += 1
                if len(top_rooms) >= 15:
                    break

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
                room_stats = {
                    "maxTemp": max(r.get("tmax", 0) for r in rooms),
                    "minTemp": min(r.get("tmin", 0) for r in rooms),
                    "maxWind": max(r.get("maxWind", 0) for r in rooms),
                    "maxPrecip": max(r.get("maxPrecip", 0) for r in rooms),
                    "maxCont37": max(r.get("maxCont37", 0) for r in rooms),
                    "maxCont38": max(r.get("maxCont38", 0) for r in rooms),
                    "maxCont40": max(r.get("maxCont40", 0) for r in rooms),
                    "maxContDaily35": max(r.get("maxContDaily35", 0) for r in rooms),
                    "maxContBelow0": max(r.get("maxContBelow0", 0) for r in rooms),
                    "maxRainHours": max(r.get("maxRainHours", 0) for r in rooms),
                    "maxDailyPrecip": max(r.get("maxDailyPrecip", 0) for r in rooms),
                    "maxPrecip3h": max(r.get("maxPrecip3h", 0) for r in rooms),
                    "maxPrecip6h": max(r.get("maxPrecip6h", 0) for r in rooms),
                    "maxPrecip12h": max(r.get("maxPrecip12h", 0) for r in rooms),
                    "maxPrecip24h": max(r.get("maxPrecip24h", 0) for r in rooms),
                    "hasHail": any(r.get("hasHail") for r in rooms),
                    "hasFreezing": any(r.get("hasFreezing") for r in rooms),
                    "hasSnow": any(r.get("hasSnow") for r in rooms),
                    "hasThunder": any(r.get("hasThunder") for r in rooms),
                    "hasFogHaze": has_fog or has_haze or has_sand,
                }
                label = self._hazard_label(room_stats)
                lines.append(f"{idx+1}. {ct}（{label}）")
                for r in rooms:
                    lines.append(f"    * {r['name']}")
                lines.append("")

            lines.append("三、关注过程")
            lines.append("")
            timeline = self._generate_timeline(
                focus_counties,
                focus_counties[0]["name"] if focus_counties else None
            )
            for entry in timeline:
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
