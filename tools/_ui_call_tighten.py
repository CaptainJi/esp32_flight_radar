#!/usr/bin/env python3
"""Tighten right-column layout + enlarge CALL panel + add VOL slider."""
from pathlib import Path
import re

p = Path("ui/ui_800x480.yaml")
t = p.read_text(encoding="utf-8")

# --- header / toolbar ---
repls = [
    # clock / coords tighter
    (
        """            id: clock_label
            align: TOP_MID
            x: 240
            y: 10""",
        """            id: clock_label
            align: TOP_MID
            x: 240
            y: 4""",
    ),
    (
        """            id: coords_label
            align: TOP_MID
            x: 240
            y: 90""",
        """            id: coords_label
            align: TOP_MID
            x: 240
            y: 58""",
    ),
    # separator under toolbar
    ('points: ["490, 176", "792, 176"]', 'points: ["490, 148", "798, 148"]'),
]

# six toolbar buttons: y 100, height 36, pitch 52 from x 492
for bid in ["map_btn", "echo_btn", "persist_btn", "atc_btn", "pwr_btn", "info_btn"]:
    repls.append(
        (
            f"id: {bid}\n            x: ",
            f"id: {bid}\n            x: ",
        )
    )

# Apply simple replacements
for a, b in [
    (
        """            id: clock_label
            align: TOP_MID
            x: 240
            y: 10""",
        """            id: clock_label
            align: TOP_MID
            x: 240
            y: 4""",
    ),
    (
        """            id: coords_label
            align: TOP_MID
            x: 240
            y: 90""",
        """            id: coords_label
            align: TOP_MID
            x: 240
            y: 58""",
    ),
    ('points: ["490, 176", "792, 176"]', 'points: ["490, 148", "798, 148"]'),
]:
    if a not in t:
        raise SystemExit(f"missing block:\n{a[:80]}")
    t = t.replace(a, b, 1)

# Toolbar y/height for the six buttons (first occurrence each)
ids = ["map_btn", "echo_btn", "persist_btn", "atc_btn", "pwr_btn", "info_btn"]
xs = [492 + i * 52 for i in range(6)]
for bid, x in zip(ids, xs):
    pat = rf"(id: {bid}\n            x: )\d+(\n            y: )\d+(\n            width: )\d+(\n            height: )\d+"
    t2, n = re.subn(pat, rf"\g<1>{x}\g<2>100\g<3>48\g<4>36", t, count=1)
    if n != 1:
        raise SystemExit(f"toolbar {bid} n={n}")
    t = t2

# Detail labels move up
t = t.replace("id: sel_cs_l\n            x: 500\n            y: 192", "id: sel_cs_l\n            x: 500\n            y: 160", 1)
t = t.replace("id: sel_type_l\n            x: 700\n            y: 188", "id: sel_type_l\n            x: 700\n            y: 156", 1)
t = t.replace("id: call_btn\n            x: 608\n            y: 188", "id: call_btn\n            x: 608\n            y: 156", 1)
t = t.replace('id: sel_route_l\n            x: 500\n            y: 228', 'id: sel_route_l\n            x: 500\n            y: 196', 1)
for old, new in [
    ("id: sel_l5, x: 500, y: 254", "id: sel_l5, x: 500, y: 222"),
    ("id: sel_l1, x: 500, y: 280", "id: sel_l1, x: 500, y: 248"),
    ("id: sel_l2, x: 500, y: 306", "id: sel_l2, x: 500, y: 274"),
    ("id: sel_l3, x: 500, y: 332", "id: sel_l3, x: 500, y: 300"),
    ("id: sel_l4, x: 500, y: 358", "id: sel_l4, x: 500, y: 326"),
]:
    if old not in t:
        raise SystemExit(f"missing {old}")
    t = t.replace(old, new, 1)

# status / brt
t = t.replace("id: status_label\n            x: 500\n            y: 452", "id: status_label\n            x: 500\n            y: 448", 1)
t = t.replace("id: brt_l\n            x: 500\n            y: 418", "id: brt_l\n            x: 500\n            y: 412", 1)
t = t.replace("id: bl_slider\n            hidden: true\n            x: 552\n            y: 426", "id: bl_slider\n            hidden: true\n            x: 552\n            y: 420", 1)

# call_panel geometry
t = t.replace(
    """            id: call_panel
            x: 490
            y: 180
            width: 302
            height: 256""",
    """            id: call_panel
            x: 490
            y: 152
            width: 308
            height: 288""",
    1,
)
t = t.replace(
    """            id: call_talk_panel
            x: 490
            y: 180
            width: 302
            height: 256""",
    """            id: call_talk_panel
            x: 490
            y: 152
            width: 308
            height: 288""",
    1,
)

# Expand call_log + shift phrase buttons + insert VOL row before TALK
old_call_inner = """              - label:
                  id: call_log_l
                  x: 10
                  y: 42
                  width: 282
                  height: 52
                  long_mode: WRAP
                  text: " "
                  text_font: font_mono
                  text_color: 0xD2E6D7
              - button:
                  id: call_p1
                  x: 10
                  y: 100
                  width: 138
                  height: 44
                  radius: 4
                  bg_color: 0x040C08
                  border_width: 1
                  border_color: 0x00A050
                  widgets:
                    - label: { align: CENTER, text: "CHECK", text_font: font_small, text_color: 0x00E66E }
                  on_click:
                    - script.execute:
                        id: voice_tx
                        phrase: "Radio check, how do you read?"
              - button:
                  id: call_p2
                  x: 154
                  y: 100
                  width: 138
                  height: 44
                  radius: 4
                  bg_color: 0x040C08
                  border_width: 1
                  border_color: 0x00A050
                  widgets:
                    - label: { align: CENTER, text: "SAY ALT", text_font: font_small, text_color: 0x00E66E }
                  on_click:
                    - script.execute:
                        id: voice_tx
                        phrase: "Say your altitude."
              - button:
                  id: call_p3
                  x: 10
                  y: 148
                  width: 138
                  height: 44
                  radius: 4
                  bg_color: 0x040C08
                  border_width: 1
                  border_color: 0x00A050
                  widgets:
                    - label: { align: CENTER, text: "IDENT", text_font: font_small, text_color: 0x00E66E }
                  on_click:
                    - script.execute:
                        id: voice_tx
                        phrase: "Ident, please."
              - button:
                  id: call_p4
                  x: 154
                  y: 148
                  width: 138
                  height: 44
                  radius: 4
                  bg_color: 0x040C08
                  border_width: 1
                  border_color: 0x00A050
                  widgets:
                    - label: { align: CENTER, text: "DESCEND", text_font: font_small, text_color: 0x00E66E }
                  on_click:
                    - script.execute:
                        id: voice_tx
                        phrase: "Request descent to flight level 240."
              - button:
                  id: call_talk_btn
                  x: 10
                  y: 196
                  width: 282
                  height: 42
                  radius: 4
                  bg_color: 0x00C060
                  border_width: 0
                  widgets:
                    - label: { align: CENTER, text: "TALK  自由对话", text_font: font_small, text_color: 0x04180C }
                  on_click:
                    - script.execute: open_call_talk"""

new_call_inner = """              - label:
                  id: call_log_l
                  x: 8
                  y: 40
                  width: 292
                  height: 72
                  long_mode: WRAP
                  text: " "
                  text_font: font_mono
                  text_color: 0xD2E6D7
              - button:
                  id: call_p1
                  x: 8
                  y: 118
                  width: 144
                  height: 40
                  radius: 4
                  bg_color: 0x040C08
                  border_width: 1
                  border_color: 0x00A050
                  widgets:
                    - label: { align: CENTER, text: "CHECK", text_font: font_small, text_color: 0x00E66E }
                  on_click:
                    - script.execute:
                        id: voice_tx
                        phrase: "Radio check, how do you read?"
              - button:
                  id: call_p2
                  x: 156
                  y: 118
                  width: 144
                  height: 40
                  radius: 4
                  bg_color: 0x040C08
                  border_width: 1
                  border_color: 0x00A050
                  widgets:
                    - label: { align: CENTER, text: "SAY ALT", text_font: font_small, text_color: 0x00E66E }
                  on_click:
                    - script.execute:
                        id: voice_tx
                        phrase: "Say your altitude."
              - button:
                  id: call_p3
                  x: 8
                  y: 162
                  width: 144
                  height: 40
                  radius: 4
                  bg_color: 0x040C08
                  border_width: 1
                  border_color: 0x00A050
                  widgets:
                    - label: { align: CENTER, text: "IDENT", text_font: font_small, text_color: 0x00E66E }
                  on_click:
                    - script.execute:
                        id: voice_tx
                        phrase: "Ident, please."
              - button:
                  id: call_p4
                  x: 156
                  y: 162
                  width: 144
                  height: 40
                  radius: 4
                  bg_color: 0x040C08
                  border_width: 1
                  border_color: 0x00A050
                  widgets:
                    - label: { align: CENTER, text: "DESCEND", text_font: font_small, text_color: 0x00E66E }
                  on_click:
                    - script.execute:
                        id: voice_tx
                        phrase: "Request descent to flight level 240."
              - label:
                  id: call_vol_l
                  x: 8
                  y: 208
                  text: "VOL"
                  text_font: font_small
                  text_color: 0xB07818
              - slider:
                  id: call_vol_sl
                  x: 52
                  y: 216
                  width: 248
                  height: 10
                  min_value: 5
                  max_value: 100
                  value: 70
                  bg_color: 0x241A08
                  bg_opa: COVER
                  radius: 5
                  indicator:
                    bg_color: 0xB07818
                  knob:
                    bg_color: 0xE8A020
                    radius: 8
                    pad_all: 4
                  on_release:
                    - number.set:
                        id: voice_vol
                        value: !lambda "return x;"
              - button:
                  id: call_talk_btn
                  x: 8
                  y: 236
                  width: 292
                  height: 42
                  radius: 4
                  bg_color: 0x00C060
                  border_width: 0
                  widgets:
                    - label: { align: CENTER, text: "TALK  自由对话", text_font: font_small, text_color: 0x04180C }
                  on_click:
                    - script.execute: open_call_talk"""

if old_call_inner not in t:
    raise SystemExit("call_panel inner block not found")
t = t.replace(old_call_inner, new_call_inner, 1)

# END button slightly wider panel: x 224
t = t.replace(
    """              - button:
                  id: call_close_btn
                  x: 218
                  y: 6
                  width: 74""",
    """              - button:
                  id: call_close_btn
                  x: 224
                  y: 6
                  width: 74""",
    1,
)

# talk panel internals widen
t = t.replace(
    """              - textarea:
                  id: ta_call
                  x: 10
                  y: 48
                  width: 282
                  height: 110""",
    """              - textarea:
                  id: ta_call
                  x: 8
                  y: 48
                  width: 292
                  height: 130""",
    1,
)
t = t.replace(
    """              - button:
                  x: 218
                  y: 6
                  width: 74
                  height: 32
                  radius: 4
                  bg_color: 0x040C08
                  border_width: 1
                  border_color: 0x00A050
                  widgets:
                    - label: { align: CENTER, text: "BACK", text_font: font_small, text_color: 0x00C060 }
                  on_click:
                    - script.execute: close_call_talk""",
    """              - button:
                  x: 224
                  y: 6
                  width: 74
                  height: 32
                  radius: 4
                  bg_color: 0x040C08
                  border_width: 1
                  border_color: 0x00A050
                  widgets:
                    - label: { align: CENTER, text: "BACK", text_font: font_small, text_color: 0x00C060 }
                  on_click:
                    - script.execute: close_call_talk""",
    1,
)
t = t.replace(
    """              - button:
                  x: 10
                  y: 168
                  width: 138
                  height: 38
                  radius: 4
                  bg_color: 0x00C060
                  border_width: 0
                  widgets:
                    - label: { align: CENTER, text: "SEND", text_font: font_small, text_color: 0x04180C }
                  on_click:
                    - script.execute: send_call_talk
              - button:
                  x: 154
                  y: 168
                  width: 138
                  height: 38""",
    """              - button:
                  x: 8
                  y: 188
                  width: 144
                  height: 40
                  radius: 4
                  bg_color: 0x00C060
                  border_width: 0
                  widgets:
                    - label: { align: CENTER, text: "SEND", text_font: font_small, text_color: 0x04180C }
                  on_click:
                    - script.execute: send_call_talk
              - button:
                  x: 156
                  y: 188
                  width: 144
                  height: 40""",
    1,
)

# atc/spec panels sync y/width lightly
t = t.replace(
    """            id: spec_panel
            x: 490
            y: 226
            width: 302
            height: 190""",
    """            id: spec_panel
            x: 490
            y: 200
            width: 308
            height: 200""",
    1,
)
t = t.replace(
    """            id: atc_panel
            x: 490
            y: 180
            width: 302
            height: 230""",
    """            id: atc_panel
            x: 490
            y: 152
            width: 308
            height: 250""",
    1,
)

p.write_text(t, encoding="utf-8")
print("ui_800x480 tightened + VOL slider")
