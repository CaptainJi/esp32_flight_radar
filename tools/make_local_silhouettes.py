#!/usr/bin/env python3
"""Draw the airframes pw-silhouettes has no picture of into data/silhouettes/.

pw-silhouettes (the source of every other drawing in aircraft_db.h) covers 104
airframes and the 747 is not one of them, so a 747 used to fall back to the
generic "heavy" sprite - a twinjet.  Rather than borrow a wrong-looking
drawing, this script plots the planform from published dimensions: fuselage,
wing (root/tip chord + sweep), tailplane and the engine nacelles, in the same
framing as the sprite sheet (nose up, length filling the tile, span to scale).

Output is our own work, plain geometry from public dimensions - no licence
attaches to it, unlike the CC BY-NC-SA sprite sheet.

    python3 tools/make_local_silhouettes.py        # writes data/silhouettes/*.png
    python3 tools/make_local_silhouettes.py --show # ASCII preview, no files

Then rerun make_aircraft_db.py to bake them into aircraft_db.h.
"""
import argparse
import math
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "silhouettes")

SS = 8          # supersampling factor - the edges are all we are drawing
TILE = 96       # output px (make_aircraft_db resamples again if --size differs)


class Plan:
    """Planform in metres, nose at y=0, centreline at x=0, +y aft."""

    def __init__(self, length, span):
        self.length, self.span = length, span
        self.polys = []

    # -- pieces ------------------------------------------------------------
    def fuselage(self, width, nose, tail_start, tail_width):
        """Slab body with a parabolic nose and a tapered tail cone."""
        h = width / 2.0
        left = [(-h * math.sqrt(t), nose * t * t) for t in
                [i / 12.0 for i in range(13)]]          # nose: x^2 profile
        left += [(-h, tail_start), (-tail_width / 2.0, self.length)]
        right = [(-x, y) for x, y in reversed(left)]
        self.polys.append(left + right)

    def wing(self, y_root, root_chord, tip_chord, semi_span, sweep_deg, y_tip=None):
        dy = semi_span * math.tan(math.radians(sweep_deg)) if y_tip is None \
            else y_tip - y_root
        half = [(0.0, y_root), (semi_span, y_root + dy),
                (semi_span, y_root + dy + tip_chord), (0.0, y_root + root_chord)]
        self.polys.append(half)
        self.polys.append([(-x, y) for x, y in half])

    def nacelle(self, x, y, length, width):
        """Engine pod: rounded-ended capsule under the wing."""
        h = width / 2.0
        self.polys.append([(x - h, y + h), (x - h, y + length - h),
                           (x - h * .7, y + length), (x + h * .7, y + length),
                           (x + h, y + length - h), (x + h, y + h),
                           (x + h * .7, y), (x - h * .7, y)])
        self.polys.append([(-p[0], p[1]) for p in self.polys[-1]])

    def fin(self, y_root, root_chord, tip_chord, height, sweep_deg):
        """Vertical tail seen from above: a thin sliver on the centreline."""
        dy = height * math.tan(math.radians(sweep_deg))
        w = 0.55                                     # half thickness at the root
        self.polys.append([(-w, y_root), (-w * .35, y_root + dy),
                           (w * .35, y_root + dy + tip_chord), (w, y_root + root_chord)])

    # -- rendering ---------------------------------------------------------
    def render(self, tile=TILE):
        n = tile * SS
        k = n / self.length                          # length fills the tile
        img = Image.new("L", (n, n), 0)
        d = ImageDraw.Draw(img)
        for p in self.polys:
            d.polygon([(x * k + n / 2.0, y * k) for x, y in p], fill=255)
        img = img.resize((tile, tile), Image.LANCZOS)
        out = Image.new("RGBA", (tile, tile), (255, 255, 255, 0))
        out.putalpha(img)
        return out


def b747_400():
    """747-400: 70.66 m long, 64.44 m span, 37.5 deg wing sweep."""
    p = Plan(70.66, 64.44)
    p.fuselage(width=6.5, nose=9.0, tail_start=52.0, tail_width=1.8)
    p.wing(y_root=25.5, root_chord=16.6, tip_chord=4.1, semi_span=32.22, sweep_deg=37.5)
    p.wing(y_root=57.6, root_chord=9.0, tip_chord=2.8, semi_span=11.1, sweep_deg=40.0)
    p.fin(y_root=55.0, root_chord=12.0, tip_chord=4.0, height=10.0, sweep_deg=45.0)
    for x, y in ((11.6, 27.5), (21.9, 36.0)):        # inboard / outboard pylons
        p.nacelle(x, y, length=8.4, width=3.1)
    return p


def b747_8():
    """747-8: 8.5 m longer, raked wingtips, same family planform."""
    p = Plan(76.25, 68.45)
    p.fuselage(width=6.5, nose=9.5, tail_start=57.0, tail_width=1.8)
    p.wing(y_root=28.0, root_chord=17.4, tip_chord=3.4, semi_span=34.22, sweep_deg=37.5)
    p.wing(y_root=62.5, root_chord=9.0, tip_chord=2.8, semi_span=11.1, sweep_deg=40.0)
    p.fin(y_root=59.5, root_chord=12.5, tip_chord=4.0, height=10.0, sweep_deg=45.0)
    for x, y in ((12.2, 30.0), (23.0, 39.0)):
        p.nacelle(x, y, length=9.2, width=3.4)
    return p


DRAWINGS = {"B744": b747_400, "B748": b747_8}


def ascii_art(img, step=2):
    a = img.split()[3].load()
    w, h = img.size
    for y in range(0, h, step):
        print("".join("#" if a[x, y] > 128 else ("." if a[x, y] > 32 else " ")
                      for x in range(w)))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", action="store_true", help="ASCII preview, write nothing")
    ap.add_argument("--size", type=int, default=TILE)
    args = ap.parse_args()
    if not args.show:
        os.makedirs(OUT, exist_ok=True)
    for code, fn in sorted(DRAWINGS.items()):
        img = fn().render(args.size)
        if args.show:
            print(f"---- {code} ----")
            ascii_art(img)
            continue
        path = os.path.join(OUT, code + ".png")
        img.save(path)
        print(f"  wrote {os.path.relpath(path, HERE)}")


if __name__ == "__main__":
    main()
