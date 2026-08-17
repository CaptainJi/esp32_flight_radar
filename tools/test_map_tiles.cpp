// Host test for the tile parser in map_tiles.h.
//
// Parsing is the one part of the map-tile feature that can be verified without
// hardware, and it is also where a mistake is invisible: a wrong record stride
// still "parses", it just yields coordinates in the wrong place. So this feeds
// it real .bin files from the tiles repo and checks the counts against what the
// generator reported.
//
// Build and run:
//     g++ -std=c++17 -DMAPTILES_HOST_TEST -I.. -o /tmp/tt tools/test_map_tiles.cpp
//     /tmp/tt ../flight-radar-maps/v1/L2/N20E120.bin 3075 44 44 74 24
//
// Arguments: <tile> <outline_pairs> <airports> <runways> <fixes> <airspaces>
// Extra tiles can follow to check that merging several accumulates correctly.
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <string>
#include <vector>

#include "../map_tiles.h"

static int failures = 0;

static void check(const char *what, long got, long want) {
  const bool ok = got == want;
  if (!ok) failures++;
  printf("  %s %-18s got %6ld  want %6ld\n", ok ? "ok  " : "FAIL", what, got, want);
}

static std::vector<uint8_t> slurp(const char *path) {
  FILE *f = fopen(path, "rb");
  if (!f) { fprintf(stderr, "cannot open %s\n", path); exit(2); }
  fseek(f, 0, SEEK_END);
  long n = ftell(f);
  fseek(f, 0, SEEK_SET);
  std::vector<uint8_t> b(n);
  if (fread(b.data(), 1, n, f) != (size_t) n) { fprintf(stderr, "short read\n"); exit(2); }
  fclose(f);
  return b;
}

int main(int argc, char **argv) {
  if (argc < 7 || (argc - 1) % 6) {
    fprintf(stderr, "usage: %s <tile> <outline_pairs> <airports> <runways> "
                    "<fixes> <airspaces> [more tiles...]\n", argv[0]);
    return 2;
  }

  long tot_out = 0, tot_ap = 0, tot_rw = 0, tot_fx = 0, tot_as = 0;
  maptiles::clear();

  for (int i = 1; i < argc; i += 6) {
    const char *path = argv[i];
    printf("%s\n", path);
    auto blob = slurp(path);
    if (!maptiles::parse(blob.data(), blob.size())) {
      printf("  FAIL parse rejected the tile\n");
      failures++;
      continue;
    }
    tot_out += atol(argv[i + 1]);
    tot_ap  += atol(argv[i + 2]);
    tot_rw  += atol(argv[i + 3]);
    tot_fx  += atol(argv[i + 4]);
    tot_as  += atol(argv[i + 5]);
    // Counts are cumulative: parse() appends, so after tile N the merged arrays
    // must hold the sum. That is exactly the property the firmware relies on.
    check("outline pairs", (long) (maptiles::OUTLINE.size() / 2), tot_out);
    check("airports", (long) maptiles::AIRPORTS.size(), tot_ap);
    check("runways", (long) maptiles::RUNWAYS.size(), tot_rw);
    check("fixes", (long) maptiles::FIXES.size(), tot_fx);
    check("airspaces", (long) maptiles::AIRSPACES.size(), tot_as);
  }
  maptiles::finish();

  printf("\nsanity checks\n");
  check("loaded", maptiles::loaded ? 1 : 0, 1);

  // Every airspace must point at a NUL-terminated name inside STRTAB and at a
  // point range inside AIRSPACE_PTS. This is what catches a rebase bug after
  // merging, which the per-tile counts above would happily miss.
  long bad_name = 0, bad_pts = 0, empty_name = 0;
  const char *base = maptiles::STRTAB.data();
  for (const auto &as : maptiles::AIRSPACES) {
    if (as.name < base || as.name >= base + maptiles::STRTAB.size()) bad_name++;
    else if (strnlen(as.name, maptiles::STRTAB.size()) == 0) empty_name++;
    if ((size_t) as.off + (size_t) as.npts * 2 > maptiles::AIRSPACE_PTS.size()) bad_pts++;
  }
  check("names in range", bad_name, 0);
  check("names non-empty", empty_name, 0);
  check("point ranges ok", bad_pts, 0);

  // Coordinates must be plausible. A wrong record stride shows up here as
  // garbage floats long before anyone squints at a rendered map.
  long bad_coord = 0;
  for (const auto &a : maptiles::AIRPORTS)
    if (!(a.lat >= -90 && a.lat <= 90 && a.lon >= -180 && a.lon <= 180)) bad_coord++;
  for (const auto &f : maptiles::FIXES)
    if (!(f.lat >= -90 && f.lat <= 90 && f.lon >= -180 && f.lon <= 180)) bad_coord++;
  for (size_t i = 0; i + 1 < maptiles::OUTLINE.size(); i += 2) {
    const float la = maptiles::OUTLINE[i];
    if (isnan(la)) continue;                       // polyline separator
    if (!(la >= -90 && la <= 90)) bad_coord++;
  }
  check("coords in range", bad_coord, 0);

  // ICAO codes are 4 characters; a stride bug shifts them into gibberish.
  long bad_icao = 0;
  for (const auto &a : maptiles::AIRPORTS) {
    if (strlen(a.icao) != 4) { bad_icao++; continue; }
    for (int k = 0; k < 4; k++)
      if (!((a.icao[k] >= 'A' && a.icao[k] <= 'Z') || (a.icao[k] >= '0' && a.icao[k] <= '9')))
        { bad_icao++; break; }
  }
  check("icao well-formed", bad_icao, 0);

  printf("\nrejection checks\n");
  {
    auto blob = slurp(argv[1]);
    maptiles::clear();
    check("truncated rejected", maptiles::parse(blob.data(), 32) ? 1 : 0, 0);

    auto bad = blob; bad[0] ^= 0xFF;
    check("bad magic rejected", maptiles::parse(bad.data(), bad.size()) ? 1 : 0, 0);

    bad = blob; bad[blob.size() - 1] ^= 0xFF;
    check("bad crc rejected", maptiles::parse(bad.data(), bad.size()) ? 1 : 0, 0);

    bad = blob; bad[6] = 0;                        // clear FLAG_COMPLETE
    check("incomplete rejected", maptiles::parse(bad.data(), bad.size()) ? 1 : 0, 0);

    // The real one: a GitHub Pages 404 is a ~9 KB HTML page, not an empty body.
    const char *html = "<!DOCTYPE html><html><head><title>Site not found</title>";
    std::vector<uint8_t> page(9379, ' ');
    memcpy(page.data(), html, strlen(html));
    check("404 html rejected", maptiles::parse(page.data(), page.size()) ? 1 : 0, 0);

    check("nothing appended", (long) maptiles::OUTLINE.size(), 0);
  }

  printf("\n%s\n", failures ? "FAILED" : "all checks passed");
  return failures ? 1 : 0;
}
