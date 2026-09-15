#!/usr/bin/env python3
"""Unify selected/focus UI colors to amber yellow (0xE8A020)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "ui/ui_800x480.yaml",
    ROOT / "ui/ui_1280x720_tab5.yaml",
    ROOT / "ui/ui_1280x720.yaml",
    ROOT / "ui/ui_1024x600.yaml",
]

def patch_ui(t: str) -> str:
    t = t.replace(
        "              bg_color: 0x00C060\n              border_color: 0x00C060",
        "              bg_color: 0xE8A020\n              border_color: 0xE8A020",
    )
    t = t.replace(
        "checked: { bg_color: 0x00A050, border_color: 0x00A050 }",
        "checked: { bg_color: 0xE8A020, border_color: 0xE8A020 }",
    )
    t = t.replace("0x04180C : 0x00C060", "0x201200 : 0x00C060")
    t = t.replace("0x04180C : 0x00E66E", "0x201200 : 0x00E66E")
    for ta in ("ta_lat", "ta_lon", "ta_rng", "ta_poll"):
        t = t.replace(
            f"lv_obj_set_style_border_color((lv_obj_t *) id({ta}), lv_color_hex(0x00E66E), 0);",
            f"lv_obj_set_style_border_color((lv_obj_t *) id({ta}), lv_color_hex(0xE8A020), 0);",
        )
    t = re.sub(
        r"(id: sel_cs_l\n(?:.*\n){0,10}? *text_color: )0x00E66E",
        r"\g<1>0xE8A020",
        t,
        count=1,
    )
    return t


def patch_core(t: str) -> str:
    # Boot: checked toolbar labels use dark-on-fill
    t = t.replace(
        "lv_obj_set_style_text_color(id(pwr_btn_l), lv_color_hex(0x04180C), 0);",
        "lv_obj_set_style_text_color(id(pwr_btn_l), lv_color_hex(0x201200), 0);",
    )
    for bid in ("map_btn_l", "echo_btn_l", "persist_btn_l", "atc_btn_l", "poff_btn_l"):
        t = t.replace(
            f"lv_obj_set_style_text_color(id({bid}), lv_color_hex(0x04180C), 0);",
            f"lv_obj_set_style_text_color(id({bid}), lv_color_hex(0x201200), 0);",
        )
    # CALL toggles selected text
    t = t.replace(
        "lv_color_hex(id(voice_radio_fx) ? 0x04180C : 0x00E66E), 0);",
        "lv_color_hex(id(voice_radio_fx) ? 0x201200 : 0x00E66E), 0);",
    )
    t = t.replace(
        "lv_color_hex(id(voice_flight_bg) ? 0x04180C : 0x00E66E), 0);",
        "lv_color_hex(id(voice_flight_bg) ? 0x201200 : 0x00E66E), 0);",
    )
    t = t.replace(
        "lv_color_hex(id(voice_lang_en) ? 0x04180C : 0x00E66E), 0);",
        "lv_color_hex(id(voice_lang_en) ? 0x201200 : 0x00E66E), 0);",
    )
    # Selected aircraft: unify to UI amber
    t = t.replace(
        "lv_color_hex(selg ? 0xFFD24A : 0x40FF9A)",
        "lv_color_hex(selg ? 0xE8A020 : 0x40FF9A)",
    )
    t = t.replace(
        "uint32_t basecol = selg ? 0xFFFFFF : (stale ? 0xFFCC00 : 0x00FF41);",
        "uint32_t basecol = selg ? 0xE8A020 : (stale ? 0xFFCC00 : 0x00FF41);",
    )
    t = t.replace(
        "uint8_t br = selg ? 0xFF : 0x40, bg = selg ? 0xD2 : 0xFF, bb = selg ? 0x4A : 0x9A;",
        "uint8_t br = selg ? 0xE8 : 0x40, bg = selg ? 0xA0 : 0xFF, bb = selg ? 0x20 : 0x9A;",
    )
    # Emergency selected blink white → amber
    t = t.replace(
        'uint32_t col = (selarr[a] && !blink) ? 0xFFFFFF : 0xFF0033;',
        'uint32_t col = (selarr[a] && !blink) ? 0xE8A020 : 0xFF0033;',
    )
    return t


def main() -> None:
    for p in FILES:
        old = p.read_text(encoding="utf-8")
        new = patch_ui(old)
        if new != old:
            p.write_text(new, encoding="utf-8")
            print(f"UI updated: {p.relative_to(ROOT)}")
        else:
            print(f"UI unchanged: {p.relative_to(ROOT)}")

    core = ROOT / "common/core.yaml"
    old = core.read_text(encoding="utf-8")
    new = patch_core(old)
    if new != old:
        core.write_text(new, encoding="utf-8")
        print("core updated")
    else:
        print("core unchanged")

    board = ROOT / "boards/m5stack_tab5.yaml"
    bold = board.read_text(encoding="utf-8")
    bnew = bold.replace(
        "lv_obj_set_style_text_color(id(pwr_btn_l), lv_color_hex(0x04180C), 0);",
        "lv_obj_set_style_text_color(id(pwr_btn_l), lv_color_hex(0x201200), 0);",
    )
    if bnew != bold:
        board.write_text(bnew, encoding="utf-8")
        print("board updated")


if __name__ == "__main__":
    main()
