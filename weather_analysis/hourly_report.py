"""Concise reports for scheduled hourly equipment-room risk checks."""

from datetime import datetime

from .warning_rules import evaluate_forecast_hazards


def _format_time(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%H:%M")
    except (TypeError, ValueError):
        return value


def _format_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%m月%d日%H时")
    except (TypeError, ValueError):
        return value


def _compact_warning_title(title: str) -> str:
    return (title or "").replace("发布", "").replace("解除", "").strip()


def _auxiliary_warning_lines(items: list[dict]) -> list[str]:
    lines = []
    for item in items:
        warning = next(iter(item.get("warnings", [])), None)
        if isinstance(warning, dict) and warning.get("title"):
            lines.append(
                f"* {item.get('county', '未分区')}：预报数据缺失；{_compact_warning_title(warning['title'])}"
            )
    return lines


def _risk_reason(room: dict) -> str:
    stats = room.get("stats", {})
    hazards = evaluate_forecast_hazards(stats)
    warning = next(iter(stats.get("officialWarnings", [])), None)
    parts = []
    labels = [hazard["name"] for hazard in hazards]
    if labels:
        parts.append("、".join(dict.fromkeys(labels[:2])))
    has_temperature_risk = stats.get("tmax") is not None and stats["tmax"] >= 37
    has_wind_risk = stats.get("maxWind", 0) >= 10
    if room.get("temperature") is not None and has_temperature_risk:
        parts.append(f"{_format_time(room.get('riskTime', ''))}温度{room['temperature']:g}℃")
    if room.get("windScale") and has_wind_risk:
        parts.append(f"风力{room['windScale']}级")
    if stats.get("maxPrecip3h", 0) >= 50:
        parts.append(f"3小时降水{stats['maxPrecip3h']:g}毫米")
    elif room.get("weatherText"):
        parts.append(room["weatherText"])
    if isinstance(warning, dict) and warning.get("title"):
        parts.append(_compact_warning_title(warning["title"]))
    return "；".join(dict.fromkeys(part for part in parts if part)) or "天气风险预警"


class HourlyReportGenerator:
    def __init__(self, region: str = "示例区域"):
        self.region = region

    @staticmethod
    def _append_section(lines: list[str], title: str, risks: list[dict], empty_text: str) -> None:
        lines.append(title)
        if not risks:
            lines.append(f"* {empty_text}")
            lines.append("")
            return
        for index, room in enumerate(risks, start=1):
            lines.append(
                f"{index}. {room.get('county', '未分区')} {room.get('name', '')}：{_risk_reason(room)}"
            )
        lines.append("")

    def generate(self, result: dict) -> str:
        start = result.get("targetStart", "")
        immediate_end = result.get("immediateEnd", "")
        outlook_end = result.get("outlookEnd", "")
        total = result.get("total", 0)
        immediate = result.get("immediateRisks", [])
        outlook = result.get("outlookRisks", [])

        lines = [f"【{self.region}机房整点天气风险（{_format_date(start)}）】", ""]
        lines.append(
            f"共检查{total}个机房，下一小时发现{len(immediate)}个高风险机房，"
            f"未来3小时发现{len(outlook)}个重点过程。"
        )
        lines.append("")
        self._append_section(
            lines,
            f"一、下一小时高风险（{_format_time(start)}-{_format_time(immediate_end)}）",
            immediate,
            "暂无达到橙色、红色数据阈值的机房。",
        )
        self._append_section(
            lines,
            f"二、未来3小时重点过程（{_format_time(start)}-{_format_time(outlook_end)}）",
            outlook,
            "暂无橙色、红色重点过程。",
        )
        if result.get("failed") or result.get("partialFailed") or result.get("warningFailed"):
            lines.append(
                "数据提示："
                f"{result.get('failed', 0)}个机房下一小时数据缺失，"
                f"{result.get('partialFailed', 0)}个机房3小时数据不完整，"
                f"{result.get('warningFailed', 0)}个机房官方预警获取失败。"
            )
        auxiliary = _auxiliary_warning_lines(result.get("auxiliaryWarnings", []))
        if auxiliary:
            lines.extend(["", "三、数据异常辅助信息", ""])
            lines.extend(auxiliary)
        return "\n".join(lines).rstrip() + "\n"
