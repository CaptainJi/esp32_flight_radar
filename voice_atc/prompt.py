"""机组角色 system prompt。"""

from __future__ import annotations

from typing import Any, Literal

Lang = Literal["zh", "en"]


def normalize_lang(lang: str | None) -> Lang:
    return "en" if (lang or "").strip().lower() in ("en", "english", "eng") else "zh"


def build_system_prompt(flight: dict[str, Any], lang: str = "zh") -> str:
    lang = normalize_lang(lang)
    cs = (flight.get("callsign") or "UNKNOWN").strip() or "UNKNOWN"
    typ = (flight.get("type") or "").strip() or "unknown type"
    reg = (flight.get("registration") or "").strip() or "n/a"
    route = (flight.get("route") or "").strip() or "unknown route"
    alt = flight.get("altitude_m")
    spd = flight.get("speed_ms")
    trk = flight.get("track_deg")
    vs = flight.get("vs_ms")
    sq = (flight.get("squawk") or "").strip() or "n/a"
    hex24 = (flight.get("icao24") or "").strip() or "n/a"
    op = (flight.get("operator") or "").strip()
    radio = (flight.get("radio_call") or "").strip()
    desc = (flight.get("description") or "").strip()

    def fmt_alt(m: Any) -> str:
        try:
            m = float(m)
        except (TypeError, ValueError):
            return "unknown"
        return f"{m:.0f} m / FL{m * 0.032808:.0f}"

    def fmt_spd(ms: Any) -> str:
        try:
            ms = float(ms)
        except (TypeError, ValueError):
            return "unknown"
        return f"{ms * 1.94384:.0f} kt"

    if lang == "en":
        lines = [
            "You are in a desktop flight-radar simulated crew radio entertainment feature.",
            "Role-play as the pilot/crew of the selected aircraft. Reply in short, spoken radio style.",
            "Hard rules:",
            "1. This is simulated, not real ATC. Never claim you can change real trajectories or receive real ATC.",
            "2. Keep replies to 1–3 sentences, radio-like, readable aloud; no markdown.",
            "3. You may use the ADS-B snapshot (callsign, altitude, speed, track); say uncertain if unknown.",
            "4. LANGUAGE LOCK: Reply ONLY in English. Do not use Chinese.",
            "5. Do not give dangerous or illegal operational advice.",
            "",
            "Selected flight snapshot:",
        ]
        open_line = f'You may open with "{cs}".'
    else:
        lines = [
            "你正在参与一个桌面飞行雷达上的「模拟机组对讲」娱乐功能。",
            "你扮演这架飞机上的飞行员/机组，用简短、口语化的陆空通话风格回答。",
            "硬性规则：",
            "1. 这是模拟，不是真实管制。禁止声称自己能改变真实航迹或接收真实 ATC 指令。",
            "2. 回答尽量 1～3 句，像对讲机：可读、可念，少用 markdown。",
            "3. 可用当前 ADS-B 快照中的呼号、高度、速度、航向；未知就说不确定。",
            "4. 语言锁定：必须只用中文回答，不要用英文。",
            "5. 不要输出危险/违法操作建议。",
            "",
            "当前选中航班快照：",
        ]
        open_line = f"开场时可自称「{cs}」。"

    lines.extend(
        [
            f"- 呼号 callsign: {cs}",
            f"- 机型 type: {typ}" + (f" ({desc})" if desc else ""),
            f"- 注册 registration: {reg}",
            f"- ICAO24: {hex24}",
            f"- 航线 route: {route}",
            f"- 高度: {fmt_alt(alt)}",
            f"- 地速: {fmt_spd(spd)}",
            f"- 航向 track: {trk if trk is not None else 'unknown'}°",
            f"- 垂直速率: {vs if vs is not None else 'unknown'} m/s",
            f"- Squawk: {sq}",
        ]
    )
    if op:
        lines.append(f"- 航司/运营人: {op}")
    if radio:
        lines.append(f"- 电台呼号 radio: {radio}")
    lines.append("")
    lines.append(open_line)
    return "\n".join(lines)
