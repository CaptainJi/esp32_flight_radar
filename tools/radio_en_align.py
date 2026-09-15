#!/usr/bin/env python3
"""RADIO panel: English labels + Tab5 toolbar/panel align."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UIS = [
    ROOT / "ui/ui_800x480.yaml",
    ROOT / "ui/ui_1024x600.yaml",
    ROOT / "ui/ui_1280x720.yaml",
    ROOT / "ui/ui_1280x720_tab5.yaml",
]

REPLACES = [
    ('text: "中"', 'text: "ZH"'),
    ('en ? "EN" : "中"', 'en ? "EN" : "ZH"'),
    ('text: "干扰"', 'text: "STATIC"'),
    ('text: "背景"', 'text: "CABIN"'),
    ('text: "自由对话"', 'text: "TALK"'),
]


def main() -> None:
    for p in UIS:
        t = p.read_text(encoding="utf-8")
        old = t
        for a, b in REPLACES:
            t = t.replace(a, b)
        if p.name == "ui_1280x720_tab5.yaml":
            # 工具栏 MAP..SYS:x=739..1280(=541);原 call_panel x=735 左探出 4px
            t = t.replace(
                """            id: call_panel
            x: 735
            y: 210
            width: 541
            height: 504""",
                """            id: call_panel
            x: 739
            y: 206
            width: 541
            height: 508""",
                1,
            )
            t = t.replace(
                """            id: call_talk_panel
            x: 735
            y: 210
            width: 541
            height: 504""",
                """            id: call_talk_panel
            x: 739
            y: 206
            width: 541
            height: 508""",
                1,
            )
            # 英文后不必为 CJK 加高;与 CHECK 行统一 54
            t = t.replace(
                """                  id: call_rfx_btn
                  x: 14
                  y: 348
                  width: 250
                  height: 60""",
                """                  id: call_rfx_btn
                  x: 14
                  y: 348
                  width: 250
                  height: 54""",
                1,
            )
            t = t.replace(
                """                  id: call_fbg_btn
                  x: 278
                  y: 348
                  width: 250
                  height: 60""",
                """                  id: call_fbg_btn
                  x: 278
                  y: 348
                  width: 250
                  height: 54""",
                1,
            )
            t = t.replace(
                """                  id: call_talk_btn
                  x: 14
                  y: 426
                  width: 513
                  height: 63""",
                """                  id: call_talk_btn
                  x: 14
                  y: 414
                  width: 513
                  height: 54""",
                1,
            )
            # 略增高日志区,容纳中英空格/句号换行
            t = t.replace(
                """                  id: call_log_l
                  x: 14
                  y: 60
                  width: 513
                  height: 81""",
                """                  id: call_log_l
                  x: 14
                  y: 60
                  width: 513
                  height: 90""",
                1,
            )
        if t != old:
            p.write_text(t, encoding="utf-8")
            print(f"updated {p.name}")
        else:
            print(f"unchanged {p.name}")

    core = ROOT / "common/core.yaml"
    ct = core.read_text(encoding="utf-8")
    ct2 = ct.replace(
        'lv_label_set_text(id(call_lang_l), id(voice_lang_en) ? "EN" : "中");',
        'lv_label_set_text(id(call_lang_l), id(voice_lang_en) ? "EN" : "ZH");',
    )
    if "ui_text.h" not in ct2:
        ct2 = ct2.replace(
            "    - kb_focus.h           # 物理鍵盤焦点(Tab5 A164;其他板为空操作)\n",
            "    - kb_focus.h           # 物理鍵盤焦点(Tab5 A164;其他板为空操作)\n"
            "    - ui_text.h            # RADIO 中英混排空格/换行\n",
        )
    if ct2 != ct:
        core.write_text(ct2, encoding="utf-8")
        print("core updated")


if __name__ == "__main__":
    main()
