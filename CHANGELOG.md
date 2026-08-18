# Changelog

Notable changes per release. Anything that changes how you flash or upgrade is called
out first, because that is the part that costs you time.

## [v1.3.0] — 2026-08-18

### ⚠️ Upgrading needs one USB flash

The map is now downloaded instead of compiled in, which required a **custom partition
table** — and a partition table cannot be changed over OTA. Coming from v1.2.0 or
earlier, flash once over USB; OTA works normally again afterwards. Your settings are
erased in the process (Wi-Fi, coordinates, Home Assistant token, alarms), so note them
down first.

To stay on the old behaviour, use the
[`pre-maptiles`](https://github.com/delphicchen/esp32_flight_radar/releases/tag/pre-maptiles)
tag — the last commit with a baked-in map and the stock partition table.

### Added

- **Downloaded map tiles.** The firmware fetches the 10°×10° tiles covering your own
  coordinates from [flight-radar-maps](https://github.com/delphicchen/flight-radar-maps)
  on first boot and stores them in a dedicated 512 KB flash partition. A prebuilt image
  now works anywhere — previously it only had a useful map near Taiwan. Coastlines,
  borders, airports, runways and navaids worldwide; Taiwan additionally gets county
  boundaries and eAIP airspace. Detail level follows the radar range.
  Progress shows under the callsign while it downloads.
- **Guition JC8048W550C / Sunton ESP32-8048S050 support** (`radar-jc8048w550.yaml`).
  Same panel controller as the generic board but an entirely different pinout, so it
  needs its own entry. Marked *alpha-test* on the installer page.
- `tools/make_tiles.py` — generates the hosted tile set; reuses `make_map.py` rather
  than reimplementing the clipping and simplification.

### Fixed

- **The browser installer was broken for every board.** GitHub stopped sending CORS
  headers on release-asset downloads, so esp-web-tools could only report
  `Failed to fetch`. Firmware is now served from the Pages site itself, same origin.
- **The installer could flash the wrong board's image.** The picker defaulted to one
  board, so reloading the page silently reset your choice, and nothing said which board
  was about to be written. Nothing is pre-selected now, and the board and version are
  named next to the button. A wrong image boots and joins Wi-Fi normally but leaves the
  screen black, which looks like dead hardware.
- **Home Assistant refused to add the device.** `api:` had no `encryption:`. The key is
  deliberately left out of the config so each device generates its own and no key ships
  inside a prebuilt image.
- **Random connection failures.** `CONFIG_LWIP_MAX_SOCKETS` was 16 where 17 are needed;
  socket exhaustion showed up as `Connection reset by peer` on the data sources.
- **A wasted request on every poll.** airplanes.live has returned 403 to everyone since
  2026-08-13, and it was tried before adsb.lol. Order swapped; it stays second in case
  it reopens.

### Changed

- Aircraft spec page: engine model and count move up to the performance figures where
  they belong, and registration, country and operator are drawn at the same size as the
  rest of the panel.
- `map_data.h` is gone. `tools/make_map.py` still produces one for custom builds, but
  nothing includes it — see [USAGE](docs/USAGE.md) if you want to bake a map in.

## [v1.2.0] — 2026-08-14

- Aircraft types on the OpenSky source, which does not report them: the type code is
  fetched once per selected aircraft and cached.
- Corrected the 747 family to four engines.

## [v1.1.0] — 2026-08-09

- **Tappable type badge**: a top-down silhouette scaled by real wingspan, revealed under
  a scan line, with manufacturer, model, dimensions, MTOW, cruise speed, registration,
  country of registry and operator — all compiled in, no lookup and no network.
- Silhouettes scaled in our own code rather than through `lv_img_set_zoom`.
- Documented the idedata cache that can flash the wrong board's image.

## [v1.0.0] — 2026-08-06

First release: live flight radar with a rotating sweep, ATC mode, weather echo from
RainViewer, map outline, four alarms, Home Assistant integration, screenshots, and
setup entirely on the touch screen.
