#!/usr/bin/env python3
"""Stretch right-column geometry so a 800*sx layout fills a wider display.

Example (Tab5): scale 1.5 yields 1200-wide content on a 1280 panel → 80px gutter.
This remaps x/width for widgets with x >= right0 so the right edge reaches dst_w.

Also stretches *relative* x/width of children inside those right-column containers,
otherwise panels grow but CHECK/VOL/log 等内部控件仍按旧宽度排列,右侧留白。
"""
from __future__ import annotations

import re
import sys
from math import floor

KEY_RE = re.compile(
    r"(?<![A-Za-z0-9_])(width|height|radius|x|y|pad_all|pad_top|pad_bottom|"
    r"pad_left|pad_right|pad_row|pad_column|border_width|line_width)"
    r"(\s*:\s*)(-?\d+)(?![\d.%A-Za-z])"
)
POINTS_RE = re.compile(r"(points\s*:\s*\[)([^\]]*)(\])")
INT_RE = re.compile(r"-?\d+")


def rnd(v: float) -> int:
    return floor(v + 0.5) if v >= 0 else -floor(-v + 0.5)


def main() -> None:
    path, right0_s, src_w_s, dst_w_s = sys.argv[1:5]
    right0, src_w, dst_w = int(right0_s), int(src_w_s), int(dst_w_s)
    if dst_w <= src_w:
        print("no stretch needed")
        return
    sx = (dst_w - right0) / float(src_w - right0)
    lines = open(path, encoding="utf-8").read().split("\n")
    out = []
    last_x = None
    # indent of the nearest ancestor whose absolute x >= right0 (None = not in right col)
    right_indent = None

    for line in lines:
        stripped = line.lstrip()
        indent = len(line) - len(stripped) if stripped else 0
        if stripped.startswith("#"):
            out.append(line)
            continue

        # when we see a new list item at page widget level (indent matching `- button:` etc), reset last_x unless this item sets x
        if stripped.startswith("-"):
            # 新同级列表项:勿继承上一项的 x,否则无绝对坐标的 keyboard
            # (align: BOTTOM_MID) 会被误拉宽超出屏宽
            last_x = None

        # 离开右侧容器(严格更外层;同级 widgets/bg_color 等不得清掉)
        if right_indent is not None and indent < right_indent:
            right_indent = None

        code, sep, comment = line, "", ""
        hash_idx = line.find("#")
        if hash_idx != -1 and '"' not in line[:hash_idx] and "'" not in line[:hash_idx]:
            code, sep, comment = line[:hash_idx], "#", line[hash_idx + 1 :]

        def pts(m):
            parts = INT_RE.findall(m.group(2))
            nums = []
            for i, p in enumerate(parts):
                v = int(p)
                if i % 2 == 0 and v >= right0:
                    v = right0 + rnd((v - right0) * sx)
                elif i % 2 == 0 and right_indent is not None and indent > right_indent:
                    v = rnd(v * sx)
                nums.append(str(v))
            body = m.group(2)
            it = iter(nums)
            body2 = INT_RE.sub(lambda _mm: next(it), body)
            return m.group(1) + body2 + m.group(3)

        code = POINTS_RE.sub(pts, code)

        xm = re.search(r"(?<![A-Za-z0-9_])x(\s*:\s*)(-?\d+)", code)
        if xm:
            last_x = int(xm.group(2))

        in_right_child = right_indent is not None and indent > right_indent

        def key_sub(m):
            nonlocal last_x, right_indent
            key, mid, val_s = m.group(1), m.group(2), m.group(3)
            val = int(val_s)
            if key == "x":
                if val >= right0:
                    right_indent = indent
                    last_x = right0 + rnd((val - right0) * sx)
                    return key + mid + str(last_x)
                if in_right_child:
                    last_x = rnd(val * sx)
                    return key + mid + str(last_x)
                last_x = val
                return m.group(0)
            if key == "width":
                if last_x is not None and last_x >= right0:
                    return key + mid + str(rnd(val * sx))
                if in_right_child:
                    return key + mid + str(rnd(val * sx))
                return m.group(0)
            return m.group(0)

        code = KEY_RE.sub(key_sub, code)
        out.append(code + sep + comment)

    open(path, "w", encoding="utf-8").write("\n".join(out))
    print(f"stretched {path}: right0={right0} {src_w}->{dst_w} sx={sx:.4f}")


if __name__ == "__main__":
    main()
