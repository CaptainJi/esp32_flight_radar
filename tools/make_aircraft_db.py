#!/usr/bin/env python3
"""Generate aircraft_db.h (type silhouettes + technical specs) for the firmware.

The firmware shows this when you tap the ICAO type badge (B738, A320, ...) in
the flight detail panel: a bright-yellow top-down silhouette of the airframe
plus manufacturer, model, wingspan, cruise speed and MTOW.

Sources (all free, all credited in the generated header and in README.md):
  silhouettes   plane-watch/pw-silhouettes GitHub release spritesheet,
                CC BY-NC-SA 4.0 - https://github.com/plane-watch/pw-silhouettes
  type/maker    ICAO Doc 8643 type designators via rikgale/ICAOList
  performance   openap (TU Delft, ~37 airliners) + tools/data/aircraft_specs.csv

Silhouettes are stored as 8-bit alpha (A8) bitmaps: LVGL paints an alpha-only
image with the widget's `image_recolor` style, which is how we get the yellow,
and A8 is the one alpha format that behaves identically on LVGL 8 (main/S3)
and LVGL 9 (lvgl9/P4).  At 96x96 that is 9.2 kB per airframe, ~1 MB total,
against ~5.8 MB of free app partition.  Use --size / --no-silhouettes to shrink.

Local, version-controlled inputs (edit these by hand, they are the point):
  tools/data/common_types.txt      which ICAO type codes to include
  tools/data/aircraft_specs.csv    span/length/MTOW/cruise for types openap
                                   does not cover; blanks render as "-"
  tools/data/silhouette_alias.csv  type -> near-identical type whose silhouette
                                   to borrow (B739 -> B738, B788 -> B789, ...)

Needs Pillow for the spritesheet (host-side only, not a firmware dependency):
    pip install pillow

    python3 tools/make_aircraft_db.py
    python3 tools/make_aircraft_db.py --size 80 --tag 20260219
"""
import argparse
import csv
import json
import math
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CACHE = os.path.join(HERE, "cache")

PW_API = "https://api.github.com/repos/plane-watch/pw-silhouettes/releases/latest"
PW_DL = "https://github.com/plane-watch/pw-silhouettes/releases/download/{tag}/{name}"
RIKGALE = "https://raw.githubusercontent.com/rikgale/ICAOList/main/"
ICAOLIST = RIKGALE + "ICAOList.csv"
AIRLINES = RIKGALE + "Airlines.csv"          # 呼號前三碼 -> 公司 + 電台呼號
HEXRANGE = RIKGALE + "ICAOHexRange.csv"      # ICAO24 區段 -> 註冊國
OPENAP_API = ("https://api.github.com/repos/TUDelft-CNS-ATM/openap/contents/"
              "openap/data/aircraft")
OPENAP_RAW = ("https://raw.githubusercontent.com/TUDelft-CNS-ATM/openap/master/"
              "openap/data/aircraft/{name}")

# engine type -> compact code stored in the header (see AcSpec::eng_t)
ENG_T = {"piston": 1, "turboprop": 2, "turboshaft": 2, "jet": 3, "electric": 4}


def get(url, path, binary=True):
    """Download url into path unless already cached."""
    if os.path.exists(path) and os.path.getsize(path) > 0:
        print(f"  cache hit: {os.path.basename(path)}")
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    print(f"  downloading {url} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "make_aircraft_db/1.0"})
    tmp = path + ".part"
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    os.replace(tmp, path)
    return path


def latest_tag():
    req = urllib.request.Request(PW_API, headers={"User-Agent": "make_aircraft_db/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["tag_name"]


# ---------------------------------------------------------------- silhouettes

def load_sprites(tag, size):
    """Return (icao -> pixel bytes, sprite_name -> icao list) at size x size A8."""
    try:
        from PIL import Image
    except ImportError:
        sys.exit("Pillow is required for the silhouettes: pip install pillow\n"
                 "(host-side only; run with --no-silhouettes to skip)")

    print(f"Fetching pw-silhouettes {tag} (CC BY-NC-SA 4.0):")
    js = get(PW_DL.format(tag=tag, name="spritesheet.json"),
             os.path.join(CACHE, f"pw-{tag}-spritesheet.json"))
    png = get(PW_DL.format(tag=tag, name="spritesheet.png"),
              os.path.join(CACHE, f"pw-{tag}-spritesheet.png"))
    with open(js, encoding="utf-8") as f:
        meta = json.load(f)

    sw = meta["metadata"]["spriteWidth"]
    sh = meta["metadata"]["spriteHeight"]
    sheet = Image.open(png).convert("RGBA")
    cols = sheet.width // sw

    # sprite name -> A8 bytes.  Animated sprites (several ids) keep frame 0.
    tiles = {}
    for name, sp in meta["sprites"].items():
        idx = sp["ids"][0]
        row, col = divmod(idx, cols)
        alpha = sheet.crop((col * sw, row * sh, col * sw + sw, row * sh + sh)).split()[3]
        if not alpha.getbbox():
            continue                      # empty slot, skip rather than ship blank
        tiles[name] = alpha.resize((size, size), Image.LANCZOS).tobytes()

    # ICAO type code -> sprite name (many types share one drawing)
    by_type = {}
    for icao, sprite in meta["airframeToSprite"].items():
        if sprite in tiles:
            by_type[icao.upper()] = sprite

    # ADS-B emitter category -> generic sprite, for types we have no drawing of.
    # pw keys them "4/3" etc: the leading digit is 4 for category A, 3 for B,
    # 2 for C, and the trailing digit is the category number (A3 -> "4/3").
    by_cat = {}
    for key, sprite in meta.get("genericToSprite", {}).items():
        head, _, num = key.partition("/")
        letter = {"4": "A", "3": "B", "2": "C"}.get(head)
        target = meta["airframeToSprite"].get(sprite, sprite)
        if letter and num.isdigit() and target in tiles:
            by_cat[letter + num] = target

    print(f"  {len(tiles)} silhouettes, {len(by_type)} type codes, "
          f"{len(by_cat)} emitter categories, "
          f"{size}x{size} A8 = {len(tiles) * size * size / 1e6:.2f} MB")
    return tiles, by_type, by_cat


# ------------------------------------------------------------------ Doc 8643

def load_icaolist():
    """ICAO type designator -> (manufacturer, model, class, n_eng, eng_type)."""
    print("Fetching ICAO Doc 8643 type designators (rikgale/ICAOList):")
    path = get(ICAOLIST, os.path.join(CACHE, "ICAOList.csv"))
    out = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            code = (row.get("Aircraft TypeDesignator") or "").strip().upper()
            if not code or code in out:
                continue                  # first row wins (list has near-dupes)
            maker, _, model = (row.get("MANUFACTURER, Model") or "").partition(",")
            neng, _, etype = (row.get("Number+Engine Type") or "").partition("/")
            etype = etype.split("/")[0].strip().lower()
            out[code] = (maker.strip(), model.strip(),
                         (row.get("Class") or "").strip(),
                         int(neng) if neng.strip().isdigit() else 0,
                         ENG_T.get(etype, 0))
    print(f"  {len(out)} designators")
    return out


def load_airlines():
    """3-letter ICAO airline code -> (company, radio callsign)."""
    print("Fetching airline codes (rikgale/ICAOList):")
    path = get(AIRLINES, os.path.join(CACHE, "Airlines.csv"))
    out = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            code = (row.get("3Ltr") or "").strip().upper()
            name = (row.get("Company") or "").strip()
            if len(code) != 3 or not code.isalpha() or not name or code in out:
                continue
            out[code] = (name[:38], (row.get("Telephony") or "").strip()[:20])
    print(f"  {len(out)} operators")
    return out


def load_hex_ranges():
    """ICAO24 address blocks -> country of registration."""
    print("Fetching ICAO24 address allocations (rikgale/ICAOList):")
    path = get(HEXRANGE, os.path.join(CACHE, "ICAOHexRange.csv"))
    out = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            if len(row) < 3:
                continue
            try:
                lo, hi = int(row[0].strip(), 16), int(row[1].strip(), 16)
            except ValueError:
                continue
            name = row[2].strip()
            if name.startswith("("):        # "(unallocated)" / "(reserved)"
                continue
            out.append((lo, hi, name[:28]))
    out.sort()
    print(f"  {len(out)} address blocks")
    return out


def engine_family(name):
    """"CFM56-7B26" -> "CFM56".  Series only, variants are noise on a 300px panel."""
    fam = (name or "").split("-")[0].strip()
    return fam[:16]


# -------------------------------------------------------------------- openap

def yaml_scalars(txt):
    """Minimal reader for openap's flat two-level aircraft yml files."""
    top, section = {}, None
    for line in txt.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^(\s*)([\w/.+-]+):\s*(.*)$", line)
        if not m:
            continue
        indent, key, val = len(m.group(1)), m.group(2), m.group(3).strip()
        if indent == 0:
            section = key if val == "" else None
            if val:
                top[key] = val
        elif section:
            top[f"{section}.{key}"] = val
    return top


def num(d, key):
    try:
        return float(d[key])
    except (KeyError, TypeError, ValueError):
        return None


def mach_to_tas_kt(mach, height_m):
    """ISA true airspeed in knots for a cruise mach at a cruise altitude."""
    t = 288.15 - 0.0065 * height_m if height_m < 11000 else 216.65
    return mach * 20.0468 * math.sqrt(t) * 1.94384


def load_openap():
    """ICAO type -> dict(span_m, len_m, mtow_kg, cruise_kt)."""
    print("Fetching openap performance data (TU Delft):")
    idx = get(OPENAP_API, os.path.join(CACHE, "openap-index.json"))
    with open(idx, encoding="utf-8") as f:
        names = [e["name"] for e in json.load(f) if e["name"].endswith(".yml")]
    out = {}
    for name in names:
        path = get(OPENAP_RAW.format(name=name), os.path.join(CACHE, "openap", name))
        with open(path, encoding="utf-8") as f:
            y = yaml_scalars(f.read())
        mach, height = num(y, "cruise.mach"), num(y, "cruise.height")
        out[name[:-4].upper()] = {
            "span_m": num(y, "wing.span"),
            "len_m": num(y, "fuselage.length"),
            "mtow_kg": num(y, "mtow"),
            "cruise_kt": mach_to_tas_kt(mach, height) if mach and height else None,
            "engine": engine_family(y.get("engine.default")),
        }
    print(f"  {len(out)} airframes")
    return out


# ------------------------------------------------------------- local CSV/TXT

def read_csv(name):
    """DictReader over a data file, ignoring the '#' comment lines around it."""
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        lines = [ln for ln in f if not ln.lstrip().startswith("#")]
    return list(csv.DictReader(lines))


def load_manual_specs():
    """tools/data/aircraft_specs.csv -> ICAO type -> dict of known values."""
    def f_(row, k):
        v = (row.get(k) or "").strip()
        try:
            return float(v) if v else None
        except ValueError:
            return None

    out = {}
    for row in read_csv("aircraft_specs.csv"):
        code = (row.get("icao") or "").strip().upper()
        if not code:
            continue
        mtow_t = f_(row, "mtow_t")
        out[code] = {"span_m": f_(row, "span_m"), "len_m": f_(row, "len_m"),
                     "mtow_kg": mtow_t * 1000 if mtow_t else None,
                     "cruise_kt": f_(row, "cruise_kt"),
                     # only used when Doc 8643 has no row for this designator
                     "mfr": (row.get("mfr") or "").strip(),
                     "model": (row.get("model") or "").strip()}
    print(f"  {len(out)} rows from tools/data/aircraft_specs.csv")
    return out


def load_engines():
    """tools/data/engines.csv -> ICAO type -> engine family."""
    out = {}
    for row in read_csv("engines.csv"):
        code = (row.get("icao") or "").strip().upper()
        eng = (row.get("engine") or "").strip()
        if code and eng:
            out[code] = eng[:16]
    print(f"  {len(out)} rows from tools/data/engines.csv")
    return out


def load_type_list():
    """tools/data/common_types.txt -> set of ICAO type codes (whitespace separated)."""
    path = os.path.join(DATA, "common_types.txt")
    if not os.path.exists(path):
        return set()
    out = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            out.update(line.split("#")[0].split())
    return {c.upper() for c in out}


def load_aliases():
    """tools/data/silhouette_alias.csv -> type code -> donor type code."""
    out = {}
    for row in read_csv("silhouette_alias.csv"):
        a = (row.get("icao") or "").strip().upper()
        b = (row.get("use_silhouette_of") or "").strip().upper()
        if a and b:
            out[a] = b
    print(f"  {len(out)} silhouette aliases")
    return out


# -------------------------------------------------------------------- output

def c_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_header(path, tag, size, tiles, order, specs, cat_sil, airlines, hexes):
    """tiles: name -> bytes, order: list of sprite names, specs: list of dicts."""
    blob = size * size
    with open(path, "w", encoding="utf-8") as f:
        f.write("// Aircraft type database generated by tools/make_aircraft_db.py"
                " - do not edit by hand\n")
        f.write(f"// silhouettes: plane-watch/pw-silhouettes {tag}, CC BY-NC-SA 4.0\n")
        f.write("//   https://github.com/plane-watch/pw-silhouettes\n")
        f.write("// designators/manufacturers/operators/ICAO24 blocks:"
                " rikgale/ICAOList (ICAO Doc 8643, Doc 8585, Annex 10)\n")
        f.write("// performance: openap (TU Delft) + tools/data/aircraft_specs.csv\n")
        f.write("// engines: openap engine.default (series only) +"
                " tools/data/engines.csv\n")
        f.write("//\n")
        f.write("// Silhouettes are 8-bit alpha (A8) bitmaps - no colour of their own.\n")
        f.write("// LVGL paints an alpha-only image with the widget's image_recolor\n")
        f.write("// style, which is where the bright yellow comes from; A8 is the one\n")
        f.write("// alpha format that behaves the same on LVGL 8 and LVGL 9.\n")
        f.write("#pragma once\n#include <stdint.h>\n#include <string.h>\n\n")

        f.write(f"inline constexpr uint16_t AC_SIL_W = {size};\n")
        f.write(f"inline constexpr uint16_t AC_SIL_H = {size};\n")
        f.write(f"inline constexpr int AC_SIL_N = {len(order)};\n")
        if order:
            f.write(f"inline const uint8_t AC_SIL_A8[{len(order)} * {blob}] = {{\n")
            for name in order:
                f.write(f"  // {name}\n")
                data = tiles[name]
                for i in range(0, len(data), 32):
                    f.write("  " + "".join(f"{b:d}," for b in data[i:i + 32]) + "\n")
            f.write("};\n\n")
        else:
            f.write("inline const uint8_t AC_SIL_A8[1] = { 0 };\n\n")

        f.write("// One row per ICAO type designator, sorted by icao for ac_spec_find().\n")
        f.write("// Zero means \"unknown\" for every numeric field - render it as a dash,\n")
        f.write("// do not print a zero wingspan.\n")
        f.write("struct AcSpec {\n")
        f.write("  char icao[5];         // \"B738\"\n")
        f.write("  const char *mfr;      // \"BOEING\"\n")
        f.write("  const char *model;    // \"737-800\"\n")
        f.write("  const char *cls;      // \"LandPlane\" / \"Helicopter\" / ...\n")
        f.write("  uint8_t eng_n;        // engine count\n")
        f.write("  uint8_t eng_t;        // 1 piston 2 turboprop/shaft 3 jet 4 electric\n")
        f.write("  const char *eng;      // engine series, \"CFM56\" - no variant\n")
        f.write("  uint16_t span_dm;     // wingspan, 0.1 m\n")
        f.write("  uint16_t len_dm;      // length, 0.1 m\n")
        f.write("  uint16_t mtow_100kg;  // max take-off weight, 100 kg\n")
        f.write("  uint16_t cruise_kt;   // cruise TAS, kt\n")
        f.write("  int16_t sil;          // AC_SIL_A8 tile index, -1 = no drawing\n")
        f.write("};\n\n")

        f.write("inline const AcSpec AC_SPECS[] = {\n")
        for s in specs:
            f.write("  { %s, %s, %s, %s, %d, %d, %s, %d, %d, %d, %d, %d },\n" % (
                c_str(s["icao"]), c_str(s["mfr"]), c_str(s["model"]), c_str(s["cls"]),
                s["eng_n"], s["eng_t"], c_str(s["eng"]), s["span_dm"], s["len_dm"],
                s["mtow_100kg"], s["cruise_kt"], s["sil"]))
        f.write("};\n")
        f.write(f"inline constexpr int AC_SPECS_LEN = {len(specs)};\n\n")

        f.write("// Binary search - AC_SPECS is sorted by icao.\n")
        f.write("inline const AcSpec *ac_spec_find(const char *ty) {\n")
        f.write("  if (ty == nullptr || *ty == 0) return nullptr;\n")
        f.write("  int lo = 0, hi = AC_SPECS_LEN - 1;\n")
        f.write("  while (lo <= hi) {\n")
        f.write("    int mid = (lo + hi) / 2;\n")
        f.write("    int c = strcmp(ty, AC_SPECS[mid].icao);\n")
        f.write("    if (c == 0) return &AC_SPECS[mid];\n")
        f.write("    if (c < 0) hi = mid - 1; else lo = mid + 1;\n")
        f.write("  }\n")
        f.write("  return nullptr;\n")
        f.write("}\n\n")

        # ---- ADS-B emitter category -> generic silhouette ----
        f.write("// Fallback drawing when the type code is unknown: the ADS-B emitter\n")
        f.write("// category (\"A3\" = large, \"A5\" = heavy, \"A7\" = rotorcraft, ...) at\n")
        f.write("// least gets the size class right.  Index [letter A/B/C][0..7], -1 = none.\n")
        f.write("inline const int16_t AC_CAT_SIL[3][8] = {\n")
        for letter in "ABC":
            row = [cat_sil.get(f"{letter}{n}", -1) for n in range(8)]
            f.write("  { " + ", ".join(str(v) for v in row) + f" }},   // {letter}0..{letter}7\n")
        f.write("};\n")
        f.write("inline int16_t ac_cat_sil(const char *cat) {\n")
        f.write("  if (cat == nullptr || cat[0] == 0 || cat[1] == 0) return -1;\n")
        f.write("  int r = cat[0] - 'A', c = cat[1] - '0';\n")
        f.write("  if (r < 0 || r > 2 || c < 0 || c > 7) return -1;\n")
        f.write("  return AC_CAT_SIL[r][c];\n")
        f.write("}\n\n")

        # ---- callsign prefix -> operator ----
        f.write("// Callsign prefix (first three letters of e.g. CAL123) -> operator.\n")
        f.write("// ICAO Doc 8585 three-letter designators; `radio` is the telephony\n")
        f.write("// callsign ATC actually says on frequency (CAL -> \"DYNASTY\").\n")
        f.write("struct AcOperator { char code[4]; const char *name; const char *radio; };\n")
        f.write("inline const AcOperator AC_OPERATORS[] = {\n")
        for code, (name, radio) in sorted(airlines.items()):
            f.write(f"  {{ {c_str(code)}, {c_str(name)}, {c_str(radio)} }},\n")
        f.write("};\n")
        f.write(f"inline constexpr int AC_OPERATORS_LEN = {len(airlines)};\n")
        f.write("inline const AcOperator *ac_operator_find(const char *cs) {\n")
        f.write("  if (cs == nullptr) return nullptr;\n")
        f.write("  char k[4] = { 0, 0, 0, 0 };\n")
        f.write("  for (int i = 0; i < 3; i++) {\n")
        f.write("    if (cs[i] < 'A' || cs[i] > 'Z') return nullptr;   // 註冊號呼號不是三碼公司代碼\n")
        f.write("    k[i] = cs[i];\n")
        f.write("  }\n")
        f.write("  int lo = 0, hi = AC_OPERATORS_LEN - 1;\n")
        f.write("  while (lo <= hi) {\n")
        f.write("    int mid = (lo + hi) / 2;\n")
        f.write("    int c = strcmp(k, AC_OPERATORS[mid].code);\n")
        f.write("    if (c == 0) return &AC_OPERATORS[mid];\n")
        f.write("    if (c < 0) hi = mid - 1; else lo = mid + 1;\n")
        f.write("  }\n")
        f.write("  return nullptr;\n")
        f.write("}\n\n")

        # ---- ICAO24 address block -> country of registration ----
        f.write("// ICAO24 (Mode S) address allocations, ICAO Annex 10 Vol III.\n")
        f.write("struct AcHexBlock { uint32_t lo, hi; const char *country; };\n")
        f.write("inline const AcHexBlock AC_HEX_BLOCKS[] = {\n")
        for lo, hi, name in hexes:
            f.write(f"  {{ 0x{lo:06X}, 0x{hi:06X}, {c_str(name)} }},\n")
        f.write("};\n")
        f.write(f"inline constexpr int AC_HEX_BLOCKS_LEN = {len(hexes)};\n")
        f.write("inline const char *ac_country_find(uint32_t addr) {\n")
        f.write("  if (addr == 0) return nullptr;\n")
        f.write("  int lo = 0, hi = AC_HEX_BLOCKS_LEN - 1;\n")
        f.write("  while (lo <= hi) {\n")
        f.write("    int mid = (lo + hi) / 2;\n")
        f.write("    if (addr < AC_HEX_BLOCKS[mid].lo) hi = mid - 1;\n")
        f.write("    else if (addr > AC_HEX_BLOCKS[mid].hi) lo = mid + 1;\n")
        f.write("    else return AC_HEX_BLOCKS[mid].country;\n")
        f.write("  }\n")
        f.write("  return nullptr;\n")
        f.write("}\n")
    print(f"wrote {path} ({os.path.getsize(path)/1e6:.1f} MB source)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(HERE, os.pardir, "aircraft_db.h"))
    ap.add_argument("--tag", help="pw-silhouettes release tag (default: latest)")
    ap.add_argument("--size", type=int, default=96, help="silhouette px (default 96)")
    ap.add_argument("--no-silhouettes", action="store_true",
                    help="specs only, no bitmaps (tiny header, for size experiments)")
    args = ap.parse_args()

    tag = args.tag or (latest_tag() if not args.no_silhouettes else "none")
    tiles, sil_by_type, sil_by_cat = ({}, {}, {})
    if not args.no_silhouettes:
        tiles, sil_by_type, sil_by_cat = load_sprites(tag, args.size)

    doc8643 = load_icaolist()
    airlines = load_airlines()
    hexes = load_hex_ranges()
    perf = load_openap()
    print("Reading local overrides:")
    manual = load_manual_specs()
    engines = load_engines()
    aliases = load_aliases()

    # Which type codes go in the table: the hand-kept list, plus everything that
    # has a drawing (no point shipping a silhouette nothing can reach).
    wanted = {c for c in load_type_list() | set(sil_by_type) if c}
    unnamed = sorted(c for c in wanted
                     if c not in doc8643 and not (manual.get(c) or {}).get("mfr"))
    if unnamed:
        print(f"  note: {len(unnamed)} codes are in neither Doc 8643 nor the mfr/model"
              f" columns of aircraft_specs.csv: {' '.join(unnamed)}")

    # Only emit tiles that some type actually reaches (directly or via alias).
    used = {sil_by_type[c] for c in wanted if c in sil_by_type}
    used |= {sil_by_type[aliases[c]] for c in wanted
             if c in aliases and aliases[c] in sil_by_type}
    used |= set(sil_by_cat.values())          # generic per-category fallbacks
    order = sorted(used)
    tile_index = {name: i for i, name in enumerate(order)}

    specs, n_span, n_sil = [], 0, 0
    for code in sorted(wanted):
        mfr, model, cls, eng_n, eng_t = doc8643.get(code, ("", "", "", 0, 0))
        v = dict(perf.get(code) or {})
        m = manual.get(code) or {}
        for k in ("span_m", "len_m", "mtow_kg", "cruise_kt"):
            if v.get(k) is None and m.get(k) is not None:
                v[k] = m[k]               # openap wins, the CSV fills the gaps
        mfr = mfr or m.get("mfr", "")     # ditto for names Doc 8643 does not list
        model = model or m.get("model", "")
        sprite = sil_by_type.get(code) or sil_by_type.get(aliases.get(code, ""), None)
        sil = tile_index.get(sprite, -1) if sprite else -1
        n_span += 1 if v.get("span_m") else 0
        n_sil += 1 if sil >= 0 else 0
        specs.append({
            "icao": code[:4], "mfr": mfr, "model": model, "cls": cls,
            "eng_n": min(eng_n, 255), "eng_t": eng_t,
            "eng": v.get("engine") or engines.get(code, ""),
            "span_dm": round((v.get("span_m") or 0) * 10),
            "len_dm": round((v.get("len_m") or 0) * 10),
            "mtow_100kg": round((v.get("mtow_kg") or 0) / 100),
            "cruise_kt": round(v.get("cruise_kt") or 0),
            "sil": sil,
        })

    n_eng = sum(1 for s in specs if s["eng"])
    cat_sil = {k: tile_index[v] for k, v in sil_by_cat.items() if v in tile_index}
    print(f"{len(specs)} type codes: {n_sil} with a silhouette, {n_span} with "
          f"dimensions, {n_eng} with an engine, {len(order)} distinct drawings")
    write_header(os.path.abspath(args.out), tag, args.size, tiles, order, specs,
                 cat_sil, airlines, hexes)


if __name__ == "__main__":
    main()
