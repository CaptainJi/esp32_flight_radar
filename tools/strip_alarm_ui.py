#!/usr/bin/env python3
"""Strip alarm_page / alarm_overlay from a scaled UI YAML for Tab5.

Usage:
  python3 tools/strip_alarm_ui.py ui/ui_1280x720.yaml ui/ui_1280x720_tab5.yaml
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def find_list_item(lines: list[str], id_substr: str) -> tuple[int, int]:
    start = -1
    for i, ln in enumerate(lines):
        if id_substr in ln and ln.lstrip().startswith("-"):
            start = i
            break
        if i + 1 < len(lines) and id_substr in lines[i + 1] and ln.lstrip().startswith("-"):
            start = i
            break
    if start < 0:
        raise SystemExit(f"list item not found: {id_substr}")
    indent = len(lines[start]) - len(lines[start].lstrip(" "))
    end = start + 1
    while end < len(lines):
        ln = lines[end]
        if not ln.strip():
            end += 1
            continue
        sp = len(ln) - len(ln.lstrip(" "))
        if sp < indent:
            break
        if sp == indent and ln.lstrip().startswith("-"):
            break
        end += 1
    return start, end


def patch_clock(lines: list[str]) -> list[str]:
    # Find clock_label, then replace its on_click actions through next sibling widget
    ci = next(i for i, ln in enumerate(lines) if ln.strip() == "id: clock_label")
    # find on_click under this label
    oc = next(i for i in range(ci, ci + 20) if lines[i].strip() == "on_click:")
    indent_oc = len(lines[oc]) - len(lines[oc].lstrip(" "))
    # actions are indented more than on_click; stop at next line with indent <= label indent
    label_indent = len(lines[ci - 1]) - len(lines[ci - 1].lstrip(" "))  # "- label:"
    # actually clock is "        - label:" then "            id:"
    # find the "- label:" line
    lab = ci - 1
    while lab > 0 and not lines[lab].lstrip().startswith("- label"):
        lab -= 1
    lab_indent = len(lines[lab]) - len(lines[lab].lstrip(" "))
    end = oc + 1
    while end < len(lines):
        ln = lines[end]
        if not ln.strip():
            end += 1
            continue
        sp = len(ln) - len(ln.lstrip(" "))
        if sp <= lab_indent:
            break
        end += 1
    new_actions = [
        " " * (indent_oc + 2) + "# Tab5:闹钟页已移除以省 RAM/CPU",
        " " * (indent_oc + 2) + "- lambda: 'ESP_LOGD(\"radar_bg\", \"alarm page disabled\");'",
    ]
    return lines[: oc + 1] + new_actions + lines[end:]


def main() -> None:
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    # splitlines 去掉 \r,避免 Windows CRLF 导致 width 正则匹配失败
    lines = src.read_text(encoding="utf-8").splitlines()

    s, e = find_list_item(lines, "id: alarm_overlay")
    if s > 0 and ("鬧鐘" in lines[s - 1] or "alarm" in lines[s - 1].lower()):
        s -= 1
    del lines[s:e]

    s, e = find_list_item(lines, "id: alarm_page")
    del lines[s:e]

    lines = patch_clock(lines)

    # 软键盘撑满 1280:scale 得 1200,否则两侧被裁/显示不全
    kb_fixed = 0
    for i, ln in enumerate(lines):
        if ln.strip() in ("id: cfg_kb", "id: call_kb"):
            for j in range(i + 1, min(i + 10, len(lines))):
                m = re.match(r"^(\s*)width:\s*\d+\s*$", lines[j])
                if m:
                    lines[j] = f"{m.group(1)}width: 1280"
                    kb_fixed += 1
                    break
                if lines[j].lstrip().startswith("- "):
                    break
    if kb_fixed < 2:
        raise SystemExit(f"strip: expected 2 keyboard widths, fixed {kb_fixed}")

    text = "\n".join(lines) + "\n"
    for bad in ("id: alarm_page", "id: alarm_overlay", "id: a0_dd", "id: spk_dd", "id: tp_overlay"):
        if bad in text:
            raise SystemExit(f"strip incomplete: still has {bad}")
    if "id: coords_label" not in text or "id: settings_page" not in text:
        raise SystemExit("strip corrupted file (missing coords/settings)")
    if "id: tz_dd" not in text:
        raise SystemExit("strip missing tz_dd (should live on settings_page)")

    header = (
        f"# Tab5 slim UI — generated from {src.name} by tools/strip_alarm_ui.py\n"
        f"# No alarm_page / alarm_overlay (RADAR_NO_ALARM). Do not edit by hand;\n"
        f"# re-run after regenerating the source layout.\n"
    )
    dst.write_text(header + text, encoding="utf-8")
    n = len(dst.read_text(encoding="utf-8").splitlines())
    print(f"wrote {dst} ({n} lines)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: strip_alarm_ui.py SRC DST")
    main()
