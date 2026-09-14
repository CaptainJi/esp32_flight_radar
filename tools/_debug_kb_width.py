#!/usr/bin/env python3
"""Debug why cfg_kb width gets stretched."""
from pathlib import Path
import re
from math import floor

path = Path("ui/ui_1280x720.yaml")
# regenerate fresh scaled without gutter first
import subprocess
subprocess.check_call([
    "python3", "tools/scale_layout.py",
    "ui/ui_800x480.yaml", "ui/_tmp1280.yaml", "1.5",
])
lines = Path("ui/_tmp1280.yaml").read_text(encoding="utf-8").split("\n")
# find cfg_kb region
for i, ln in enumerate(lines):
    if "id: cfg_kb" in ln:
        print("BEFORE gutter, around cfg_kb:")
        for j in range(i - 25, i + 8):
            print(f"{j}: {lines[j]}")
        break

# simulate gutter
right0, src_w, dst_w = 735, 1200, 1280
sx = (dst_w - right0) / float(src_w - right0)
KEY_RE = re.compile(
    r"(?<![A-Za-z0-9_])(width|height|radius|x|y|pad_all|pad_top|pad_bottom|"
    r"pad_left|pad_right|pad_row|pad_column|border_width|line_width)"
    r"(\s*:\s*)(-?\d+)(?![\d.%A-Za-z])"
)
last_x = None
right_indent = None

def rnd(v):
    return floor(v + 0.5) if v >= 0 else -floor(-v + 0.5)

for i, line in enumerate(lines):
    stripped = line.lstrip()
    indent = len(line) - len(stripped) if stripped else 0
    if stripped.startswith("#"):
        continue
    if stripped.startswith("-"):
        last_x = None
    if right_indent is not None and indent < right_indent:
        right_indent = None
    xm = re.search(r"(?<![A-Za-z0-9_])x(\s*:\s*)(-?\d+)", line)
    if xm:
        val = int(xm.group(2))
        old = last_x
        if val >= right0:
            right_indent = indent
            last_x = right0 + rnd((val - right0) * sx)
        elif right_indent is not None and indent > right_indent:
            last_x = rnd(val * sx)
        else:
            last_x = val
    wm = re.search(r"(?<![A-Za-z0-9_])width(\s*:\s*)(-?\d+)", line)
    if wm and "cfg_kb" in "\n".join(lines[max(0,i-5):i+1]):
        val = int(wm.group(2))
        stretch = last_x is not None and last_x >= right0
        print(f"LINE {i} width={val} last_x={last_x} stretch={stretch} -> {rnd(val*sx) if stretch else val}")
        print(f"  line={line!r}")
        print(f"  context={[lines[j] for j in range(i-6,i+1)]}")

Path("ui/_tmp1280.yaml").unlink(missing_ok=True)
