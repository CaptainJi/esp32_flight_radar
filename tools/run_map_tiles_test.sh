#!/usr/bin/env bash
# Run the host test for the map-tile parser (map_tiles.h) against real tiles.
#
# The expected record counts are derived here in Python straight from each
# tile's header, and checked in C++ by the parser under test. Two independent
# readings of the same bytes -- typing the numbers by hand instead would just
# test that they were copied correctly, and a wrong record stride would sail
# through (it did, while these were guessed by hand).
#
# Usage:  tools/run_map_tiles_test.sh [tiles-repo-dir]
set -euo pipefail
cd "$(dirname "$0")/.."
MAPS="${1:-../flight-radar-maps}"

[ -d "$MAPS/v1" ] || { echo "no tiles at $MAPS/v1 -- clone flight-radar-maps or pass its path" >&2; exit 1; }

BIN="$(mktemp -d)/test_map_tiles"
g++ -std=c++17 -DMAPTILES_HOST_TEST -Wall -Wextra -o "$BIN" tools/test_map_tiles.cpp

# A spread of levels and continents, including the two Taiwan cells (the only
# ones with airspace) and one southern-hemisphere cell.
TILES="v1/L2/N20E120.bin v1/L2/N20E110.bin v1/L2/N50E010.bin v1/L3/N40W080.bin v1/L1/S40W070.bin"

ARGS=$(python3 - "$MAPS" $TILES <<'PY'
import struct, sys, os
maps, tiles = sys.argv[1], sys.argv[2:]
HF = "<4sHHIffBBH"; hs = struct.calcsize(HF)
out = []
for rel in tiles:
    path = os.path.join(maps, rel)
    b = open(path, "rb").read()
    tbl = [struct.unpack_from("<II", b, hs + i * 8) for i in range(5)]
    pay = b[hs + 40:]
    nas = struct.unpack_from("<HH", pay, tbl[4][0])[0] if tbl[4][1] else 0
    # section length / on-the-wire record size
    out += [path, str(tbl[0][1] // 8), str(tbl[1][1] // 13),
            str(tbl[2][1] // 32), str(tbl[3][1] // 14), str(nas)]
print(" ".join(out))
PY
)

exec "$BIN" $ARGS
