"""Weather warning rules used by the equipment-room risk report.

The rules below model public national meteorological warning thresholds where
the forecast data has the needed fields, and add conservative equipment-room
attention rules for risks that the forecast API exposes only partially.
"""

LEVEL_SCORE = {
    "提示": 0,
    "蓝色": 1,
    "黄色": 2,
    "橙色": 3,
    "红色": 4,
}

REPORT_LEVEL = {
    "红色": "红色预警",
    "橙色": "橙色关注",
    "黄色": "黄色注意",
    "蓝色": "蓝色提示",
    "提示": "一般关注",
}

COLOR_BY_SCORE = {
    1: "蓝色",
    2: "黄色",
    3: "橙色",
    4: "红色",
}

HAZARD_PRIORITY = {
    "冰雹": 120,
    "冻雨": 115,
    "道路结冰": 110,
    "暴雨": 100,
    "强降水": 95,
    "红色高温": 90,
    "橙色高温": 85,
    "高温": 80,
    "红色大风": 75,
    "橙色大风": 72,
    "大风": 70,
    "强风": 65,
    "暴雪": 60,
    "降雪": 55,
    "雷暴": 50,
    "雾霾": 30,
}


def _value(data, *names, default=0):
    for name in names:
        if name in data and data[name] is not None:
            return data[name]
    return default


def _temp_max(data):
    return _value(data, "maxTemp", "tmax")


def _temp_min(data):
    return _value(data, "minTemp", "tmin")


def _hazard(name, level, source, score_bonus=0):
    return {
        "name": name,
        "level": level,
        "source": source,
        "severity": LEVEL_SCORE[level],
        "priority": HAZARD_PRIORITY.get(name, 0),
        "score": LEVEL_SCORE[level] * 100 + HAZARD_PRIORITY.get(name, 0) + score_bonus,
    }


def _official_hazard_name(type_name, level):
    if "高温" in type_name:
        if level == "红色":
            return "红色高温"
        if level == "橙色":
            return "橙色高温"
        return "高温"
    if "大风" in type_name:
        if level == "红色":
            return "红色大风"
        if level == "橙色":
            return "橙色大风"
        return "大风"
    return type_name or "官方预警"


def _hazard_category(name):
    if "高温" in name:
        return "高温"
    if "大风" in name or name == "强风":
        return "大风"
    if name in {"暴雨", "强降水"}:
        return "降水"
    if name in {"冻雨", "道路结冰"}:
        return "结冰"
    if name in {"暴雪", "降雪"}:
        return "降雪"
    return name


def _dedupe_hazards(hazards):
    by_category = {}
    for hazard in hazards:
        category = _hazard_category(hazard["name"])
        current = by_category.get(category)
        if current is None or hazard["score"] > current["score"]:
            by_category[category] = hazard
    return list(by_category.values())


def evaluate_hazards(data):
    hazards = []

    max_temp = _temp_max(data)
    min_temp = _temp_min(data)
    max_wind = _value(data, "maxWind")
    max_precip = _value(data, "maxPrecip")
    max_precip_3h = _value(data, "maxPrecip3h")
    max_precip_6h = _value(data, "maxPrecip6h")
    max_precip_12h = _value(data, "maxPrecip12h")
    max_precip_24h = _value(data, "maxPrecip24h", "maxDailyPrecip")
    max_cont_daily_35 = _value(data, "maxContDaily35")

    official_warnings = data.get("officialWarnings") or []
    if official_warnings:
        top = max(official_warnings, key=lambda w: w.get("levelScore", 0))
        score = int(top.get("levelScore") or 0)
        level = COLOR_BY_SCORE.get(score)
        if level:
            type_name = top.get("typeName") or "官方预警"
            hazards.append(_hazard(_official_hazard_name(type_name, level), level, "qweather_warning", score_bonus=80))

    if max_temp > 40:
        hazards.append(_hazard("红色高温", "红色", "national"))
    elif max_temp > 37:
        hazards.append(_hazard("橙色高温", "橙色", "national"))
    elif max_cont_daily_35 >= 3:
        hazards.append(_hazard("高温", "黄色", "national"))

    if max_precip_3h >= 100:
        hazards.append(_hazard("暴雨", "红色", "national"))
    elif max_precip_3h >= 50:
        hazards.append(_hazard("暴雨", "橙色", "national"))
    elif max_precip_6h >= 50:
        hazards.append(_hazard("暴雨", "黄色", "national"))
    elif max_precip_12h >= 50 or max_precip_24h >= 50:
        hazards.append(_hazard("暴雨", "蓝色", "national"))
    elif max_precip >= 8:
        hazards.append(_hazard("强降水", "黄色", "telecom_attention"))

    if max_wind >= 12:
        hazards.append(_hazard("红色大风", "红色", "national"))
    elif max_wind >= 10:
        hazards.append(_hazard("橙色大风", "橙色", "national"))
    elif max_wind >= 8:
        hazards.append(_hazard("大风", "黄色", "national"))
    elif max_wind >= 6:
        hazards.append(_hazard("强风", "蓝色", "national"))

    if data.get("hasHail"):
        hazards.append(_hazard("冰雹", "红色", "telecom_attention"))
    if data.get("hasFreezing"):
        hazards.append(_hazard("冻雨", "红色", "telecom_attention"))
    if min_temp <= 0 and (
            data.get("hasFreezing") or data.get("hasSnow") or max_precip > 0 or max_precip_24h > 0):
        hazards.append(_hazard("道路结冰", "黄色", "telecom_attention"))
    if data.get("hasSnow"):
        hazards.append(_hazard("暴雪" if min_temp <= -5 else "降雪", "黄色", "telecom_attention"))
    if data.get("hasThunder"):
        hazards.append(_hazard("雷暴", "黄色", "telecom_attention"))
    if data.get("hasFogHaze") or data.get("hasFog") or data.get("hasHaze") or data.get("hasSand"):
        hazards.append(_hazard("雾霾", "黄色", "telecom_attention"))

    hazards = _dedupe_hazards(hazards)
    hazards.sort(key=lambda h: (h["severity"], h["priority"]), reverse=True)
    return hazards


def warning_level(data):
    hazards = evaluate_hazards(data)
    if not hazards:
        return None
    return hazards[0]["level"]


def report_level(items):
    best = None
    for item in items:
        level = warning_level(item)
        if level and (best is None or LEVEL_SCORE[level] > LEVEL_SCORE[best]):
            best = level
    return REPORT_LEVEL.get(best) if best else None


def risk_score(data):
    hazards = evaluate_hazards(data)
    score = max((h["score"] for h in hazards), default=0)
    score += min(_value(data, "warnedCount"), 100)
    score += min(_value(data, "maxCont37") * 5, 50)
    score += min(_value(data, "maxRainHours") * 4, 40)
    score += min(_value(data, "maxPrecip") * 2, 60)
    return score


def is_warning(data):
    return bool(evaluate_hazards(data))


def is_significant(data):
    return max((h["severity"] for h in evaluate_hazards(data)), default=0) >= LEVEL_SCORE["橙色"]


def is_focus_warning(data):
    return is_significant(data)
