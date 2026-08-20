#!/usr/bin/env bash
# Build richer map tiles for eastern China (provinces + rivers + major roads + rail).
# Official CDN tiles usually only have coastline/country borders.
#
# Usage (from repo root, WSL/Linux):
#   ./tools/build_china_map_tiles.sh
#   ./tools/build_china_map_tiles.sh /path/to/flight-radar-maps
#
# Then host the output on GitHub Pages and set in radar-*.yaml / common/core.yaml:
#   substitutions:
#     maps_base_url: "https://<you>.github.io/flight-radar-maps/v1"
#
# Force the device to re-download: change range slightly, or erase maps partition
# by USB reflashing a factory image.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/../flight-radar-maps}"
# Qingdao / Shandong / Bohai / Jiangsu-ish cells for ~300 km around 36N 120E
CELLS="N30E110,N30E120,N40E110,N40E120"

mkdir -p "$OUT"
python3 "$ROOT/tools/make_tiles.py" \
  --out "$OUT" \
  --cells "$CELLS" \
  --levels 1,2,3 \
  --states \
  --rivers \
  --roads \
  --railroads \
  --min-airport medium

echo
echo "Tiles written under $OUT/v1/"
echo "Push that repo to GitHub Pages, then set maps_base_url to its /v1 URL."
