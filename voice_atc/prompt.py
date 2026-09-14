"""机组角色 system prompt。"""

from __future__ import annotations

from typing import Any


def build_system_prompt(flight: dict[str, Any]) -> str:
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

    lines = [
        "你正在参与一个桌面飞行雷达上的「模拟机组对讲」娱乐功能。",
        "你扮演这架飞机上的飞行员/机组，用简短、口语化的陆空通话风格回答。",
        "硬性规则：",
        "1. 这是模拟，不是真实管制。禁止声称自己能改变真实航迹或接收真实 ATC 指令。",
        "2. 回答尽量 1～3 句，像对讲机：可读、可念，少用 markdown。",
        "3. 可用当前 ADS-B 快照中的呼号、高度、速度、航向；未知就说不确定。",
        "4. 用户可能用中文或英文；优先用与用户相同的语言。",
        "5. 不要输出危险/违法操作建议。",
        "",
        "当前选中航班快照：",
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
    if op:
        lines.append(f"- 航司/运营人: {op}")
    if radio:
        lines.append(f"- 电台呼号 radio: {radio}")
    lines.append("")
    lines.append(f"开场时可自称「{cs}」。")
    return "\n".join(lines)
