# ✈️ ESP32 Flight Radar

A desktop flight-radar ornament for the **ESP32-S3 5" 800×480 RGB touch panel**, built entirely with **ESPHome**. It shows live aircraft over your location on an ATC-style radar scope, and doubles as a weather-radar display, a Home Assistant panel, and an alarm clock.

> 一款以 **ESPHome** 打造的桌面航班雷達擺件,執行於 **ESP32-S3 5 吋 800×480 RGB 觸控屏**。以航管雷達風格顯示你所在位置上空的即時航班,同時也是氣象雷達顯示器、Home Assistant 控制面板與鬧鐘。

Inspired by [AnthonySturdy/micro-radar](https://github.com/AnthonySturdy/micro-radar) — reimagined for a large landscape touch display with a much larger feature set.

---

**[English](#english) · [中文](#中文)**

## 📸 Demo / 畫面

![ESP32 Flight Radar demo](docs/demo.gif)

## 🎬 Demo video / 示範影片

▶ **[Watch the full demo video / 觀看完整示範影片](docs/demo.mp4)**


---

## English

### Features

- **Live flight radar** — pulls aircraft states from the [OpenSky Network](https://opensky-network.org/), [airplanes.live](https://airplanes.live/) or [adsb.lol](https://adsb.lol/) around your coordinates and plots them on a 480×480 radar scope (up to **40 aircraft**, nearest first) with a rotating sweep, fading trail, and target glow as the beam passes each aircraft.
- **Selectable data source + automatic fallback** — an **ADS-B SRC** dropdown on the settings page picks OpenSky (OAuth2, 4,000 credits/day) or the free no-key **airplanes.live** / **adsb.lol** APIs. A single **POLL** field sets the interval and follows the selected source (each source keeps its own stored value, so switching back restores it). If an OpenSky fetch fails (bad credentials, quota exhausted, outage) the device automatically falls back to the free sources for 10 minutes, then retries OpenSky; the status line and SYS panel show which source is active.
- **ATC-style labels** — each aircraft shows its callsign, flight level and speed, with a heading-oriented plane icon. Tap any aircraft to see its **origin → destination** (via [adsbdb.com](https://www.adsbdb.com/)), **squawk** (turns red on 7500/7600/7700), altitude, speed, heading, vertical rate, distance and bearing, plus the **ICAO type code** as a highlighted badge next to the callsign (type is only published by airplanes.live / adsb.lol, so the badge is hidden under OpenSky).
- **ATC mode** — toggle button switches the plane icons to bare **target squares** with a **2‑minute velocity vector**, a **dotted fading history trail**, and a local **STCA-style conflict alert** (two aircraft within 5.5 km / 300 m get flagged red); stale data (no update for 60 s) is flagged yellow with a `*` suffix. Turn it off to instantly restore the normal plane-icon view.
- **Weather echo overlay** — optional rain-radar layer from [RainViewer](https://www.rainviewer.com/), downloaded, decoded and composited **entirely on a background core** so the UI never stutters. Toggle with an on-screen button.
- **Map outline overlay** — optional coastline / administrative border layer (Taiwan by default), toggle on screen.
- **Home Assistant integration** — the device auto-discovers in HA; backlight, Wi-Fi signal and buttons become HA entities.
- **Alarm clock** — up to 4 alarms, each with per-weekday scheduling. Alarms ring through a **Home Assistant media player** (any Wi-Fi speaker); **each alarm can ring on its own speaker** (e.g. weekday alarm in the bedroom, weekend alarm in the living room). On boards with onboard audio (Waveshare **ESP32-P4-WIFI6-Touch-LCD-7B**) the dropdown also offers **LOCAL SPEAKER**, which beeps from the board itself with no Home Assistant involved. On-screen **Snooze / Dismiss** overlay when ringing.
- **Fully on-device setup** — first boot opens a Wi-Fi captive portal. Coordinates, scan range, poll interval, OpenSky credentials and the alarm speaker can all be entered **on the touch screen** (or via the web page / Home Assistant). A **timezone** dropdown (alarm page, with each city's UTC offset) and a **UNIT** dropdown (settings page — METRIC/IMPERIAL switches °C/°F, km·h/mph, km/mi, m/ft, m·s/fpm and the RANGE field itself; flight levels and knots stay as they are) are set on screen too. Everything is stored in NVS and survives reboots.
- **Night mode on boards without a dimmable backlight** — on the Waveshare Touch-LCD-5/5B the backlight sits on a CH422G expander pin with no PWM, so it can only be switched on or off. On those boards the brightness slider drives a full-screen dark overlay instead, which dims perceived brightness and persists across reboots. It does not reduce power draw.
- **OTA updates** — after the first USB flash, all future updates are wireless.

### Hardware

| Part | Detail |
|------|--------|
| Board | ESP32-S3 5" RGB panel board (`esp32-s3-5inch-rgb-001`), 8 MB PSRAM (octal) + 16 MB flash |
| Panel | 800×480 IPS, ST7262 RGB driver |
| Touch | GT911 capacitive (I²C) |
| Power | USB-C |
| Enclosure | 3D-printable case ships with the board's SDK |

### Supported boards

| Entry | Board | MCU | Panel | Wi-Fi | Status |
|-------|-------|-----|-------|-------|--------|
| `radar.yaml` | esp32-s3-5inch-rgb-001 (generic) | ESP32-S3 | 800×480 parallel-RGB (ST7262) | native | **verified on hardware** |
| `radar-s3-5.yaml` | Waveshare ESP32-S3-Touch-LCD-5 | ESP32-S3 | 800×480 parallel-RGB (ST7262) | native | config + build verified, **not yet flashed** |
| `radar-s3-5b.yaml` | Waveshare ESP32-S3-Touch-LCD-5B | ESP32-S3 | 1024×600 parallel-RGB | native | **verified on hardware** |
| `radar-p4-7b.yaml` | Waveshare ESP32-P4-WIFI6-Touch-LCD-7B | ESP32-P4 | 1024×600 MIPI-DSI (EK79007) | ESP32-C6 (esp-hosted/SDIO) | **verified on hardware** — but use `lvgl9` for microSD + screenshots |

> **Which branch do I use?** The two branches are not "old" and "new" — each one
> serves different boards, and both are maintained:
>
> | Board | Branch | ESPHome | LVGL |
> |-------|--------|---------|------|
> | the three **ESP32-S3** boards | `main` (you are here) | 2026.3.3 | 8.4 |
> | **ESP32-P4** Touch-LCD-7B | `lvgl9` | 2026.6.5 | 9.5 |
>
> `radar-p4-7b.yaml` builds and runs from this branch, but **without microSD support or
> screenshots** — both need a component that only loads on the newer ESPHome. If you
> have the P4 board, use the `lvgl9` branch. The S3 boards stay here because LVGL 9
> measurably slowed the radar sweep down on them.

Common requirements for the RGB boards: **≥8 MB octal PSRAM** (quad-PSRAM can't feed
the RGB panel), a **GT911** I²C touch controller, and 16 MB flash (`flash_size` is set
per board). Other generic 800×480 RGB+GT911 boards (Sunton ESP32-8048S050, Guition
JC8048W550, …) work with `radar.yaml` after matching the pins in
`boards/esp32s3_rgb_800x480.yaml`.

More detail — project layout, per-board timings/pin caveats, the local component
overrides and how to add a board — is in **[docs/BOARDS.md](docs/BOARDS.md)**.

### Software requirements

- **[ESPHome](https://esphome.io/) 2026.3.x is recommended** (`pip install esphome==2026.3.*`). The firmware calls the LVGL **v8** canvas draw API directly, so it does **not** build on 2026.4.0+ (which switched to LVGL v9) — see issue #5. The 1024×600 boards additionally need the `mipi_rgb` / `mipi_dsi` drivers added in 2025.9.0, so their working range is **2025.9 – 2026.3** (2026.3.x covers all three boards). The original 800×480 `radar.yaml` works on any ≤ 2026.3.x.
- The dependency `pngle` is pulled in automatically via `platformio_options`.

### Flashing

```bash
git clone https://github.com/delphicchen/esp32_flight_radar
cd esp32_flight_radar
esphome run radar.yaml          # ESP32-S3 800×480 (original board)
# or, for the newer panels:
# esphome run radar-s3-5.yaml   # Waveshare ESP32-S3-Touch-LCD-5   (800×480)
# esphome run radar-s3-5b.yaml  # Waveshare ESP32-S3-Touch-LCD-5B  (1024×600)
# esphome run radar-p4-7b.yaml  # Waveshare ESP32-P4-WIFI6-Touch-LCD-7B (1024×600)
```

First flash must be over **USB** (`/dev/ttyUSB0` or `/dev/ttyACM0`; add yourself to the `dialout` group on Linux). If the upload stalls, hold **BOOT**, tap **RESET**, release **BOOT** to enter download mode. After that, `esphome run` updates over the air.

### First-time setup

1. On first boot the panel opens a Wi-Fi hotspot **`Radar-Setup`** (password `12345678`). Connect with your phone and pick your home Wi-Fi in the captive portal.
2. *(Only needed for the OpenSky source)* Register a **free OpenSky account**, then create an **API Client** in your account settings — this gives you a `client_id` and `client_secret` (OpenSky uses OAuth2, not your login password). If you pick **airplanes.live** or **adsb.lol** as the source instead, no account or key is required at all.
3. Tap the **Wi-Fi icon** (top right) or the **status line** to open the network / API page and enter your OpenSky credentials on screen. You can also fill them at `http://flight-radar.local` or in Home Assistant.
4. Tap the **coordinates line** to set your latitude / longitude, scan range and OpenSky poll interval on the numeric keypad; the **SRC** row picks the data source (OPENSKY / A.LIVE / ADSB.LOL) and **POLL2** sets the poll interval used with the free sources; a checkbox chooses whether fetching **continues while the backlight is off** (default: paused). With OpenSky selected the page shows a live estimate of the resulting **daily API credit usage** (green / amber / red against the free 4,000-credit quota; cost per fetch grows with range); the free sources have no daily quota but cap the radius at 250 NM (≈463 km).
5. Aircraft should appear within a minute. Toggle **MAP** / **ECHO** as you like.

### Configuration reference

All of these are Home Assistant / web entities, stored in NVS:

| Setting | Meaning |
|---------|---------|
| OpenSky Client ID / Secret | OAuth2 API client credentials |
| Home Latitude / Longitude | Radar center (your location) |
| Radar Range | Scan radius in km (10–500) |
| Poll Interval | Seconds between OpenSky fetches (10–300, default 30 → 2880/day, within the 4000/day quota) |
| Poll Interval Alt | Seconds between fetches on the free sources (airplanes.live / adsb.lol, 5–300, default 15) |
| | On screen there is only one **POLL** box — it edits whichever of the two matches the selected **ADS-B SRC**, so both values stay stored independently. |
| HA URL | Home Assistant address for speaker scan (empty = `http://homeassistant.local:8123`) |
| HA Token | HA long-lived access token used by the SCAN button |
| Alarm Speaker | Default HA `media_player` entity to ring through (type it or use SCAN) |
| Alarm 1–4 Speaker | Per-alarm speaker override; empty = use Alarm Speaker |
| Alarm Sound URL | mp3 to play when an alarm fires |

### Going further

- **[docs/USAGE.md](docs/USAGE.md)** — alarms (incl. Google Nest speakers), ATC
  mode, screenshots to Home Assistant, using the radar outside Taiwan
- **[docs/BOARDS.md](docs/BOARDS.md)** — board wiring, panel timings, component
  overrides, and the settings already ruled out on hardware

### Data sources & credits

- Aircraft states — [OpenSky Network](https://opensky-network.org/), [airplanes.live](https://airplanes.live/), [adsb.lol](https://adsb.lol/)
- Route lookup — [adsbdb.com](https://www.adsbdb.com/)
- Weather radar — [RainViewer](https://www.rainviewer.com/)
- Local weather — [Open-Meteo](https://open-meteo.com/)
- Taiwan boundaries — [g0v/twgeojson](https://github.com/g0v/twgeojson)
- World map data — [Natural Earth](https://www.naturalearthdata.com/) (public domain)
- Airports / runways / navaids — [OurAirports](https://ourairports.com/) (public domain)
- Taiwan airspace boundaries — [Taiwan CAA eAIP](https://ais.caa.gov.tw/) ENR 2.1
- Airspace boundaries elsewhere (optional) — [openAIP](https://www.openaip.net/) (CC BY-NC)
- microSD storage components (used on the `lvgl9` branch) — [p1ngb4ck's ESPHome fork](https://github.com/p1ngb4ck/esphome)
- Concept — [AnthonySturdy/micro-radar](https://github.com/AnthonySturdy/micro-radar)
- Climb/descent arrow glyphs — [DejaVu Sans](https://dejavu-fonts.github.io/) (Bitstream Vera / DejaVu license, `fonts/DejaVuSans.ttf`)

Please respect each provider's free-tier terms; this project is a hobby build, not a service.

---

## 中文

### 功能

- **即時航班雷達** — 從 [OpenSky Network](https://opensky-network.org/)、[airplanes.live](https://airplanes.live/) 或 [adsb.lol](https://adsb.lol/) 取得你座標周圍的航班,繪製在 480×480 雷達盤上(最多 **40 架**,由近而遠),附旋轉掃描線、漸暗餘暉,以及掃描線掃過飛機時的高亮效果。
- **可選資料來源 + 自動備援** — 設定頁的 **ADS-B SRC** 下拉可選 OpenSky(OAuth2,每日 4000 credits)或免金鑰的 **airplanes.live** / **adsb.lol** 免費 API。只有一個 **POLL** 欄位,會跟著所選來源自動切換(兩個來源各自記住自己的值,切回去就還原)。OpenSky 抓取失敗(憑證錯誤、額度用盡、服務中斷)會自動改用免費來源 10 分鐘後再回試;狀態列與 SYS 面板會顯示目前實際來源。
- **航管風格標籤** — 每架飛機顯示呼號、飛航高度層與速度,搭配依航向旋轉的飛機圖示。點選任一飛機可查看**起點 → 目的地**(透過 [adsbdb.com](https://www.adsbdb.com/))、**squawk**(7500/7600/7700 轉紅)、高度、速度、航向、垂直速率、距離與方位,呼號旁還有反白的 **ICAO 機型徽章**(只有 airplanes.live / adsb.lol 提供機型,OpenSky 下徽章會隱藏)。
- **ATC 模式** — 按鈕切換,飛機圖示換成純**目標方塊**,附**未來 2 分鐘速度向量線**、**漸淡的點線歷史軌跡**,以及本地端 **STCA 風格衝突告警**(兩機水平距離 < 5.5km 且高度差 < 300m 觸發紅色);資料超過 60 秒未更新則標為黃色並加 `*`。再按一次立即還原成預設的飛機圖示畫面。
- **氣象回波圖層** — 可選的降雨雷達層,資料來自 [RainViewer](https://www.rainviewer.com/);下載、解碼、合成**全部在背景核心完成**,主畫面完全不卡。以螢幕按鈕開關。
- **地圖輪廓圖層** — 可選的海岸線 / 行政區界(預設台灣),螢幕按鈕開關。
- **Home Assistant 整合** — 裝置會自動被 HA 探索;背光、Wi-Fi 訊號與按鈕都成為 HA 實體。
- **鬧鐘** — 最多 4 組,每組可設定特定星期幾。鬧鐘透過 **Home Assistant 的媒體播放器**(任何 Wi-Fi 喇叭)發聲,且**每組鬧鐘可指定不同喇叭**(例如平日鬧鐘在臥室響、週末鬧鐘在客廳響)。板子本身有音訊硬體時(微雪 **ESP32-P4-WIFI6-Touch-LCD-7B**),下拉選單還會多一項 **LOCAL SPEAKER**,由板載喇叭直接發出提示音,完全不經 Home Assistant。響鈴時螢幕出現**貪睡 / 關閉**面板。
- **完全在裝置上設定** — 首次開機開啟 Wi-Fi 設定熱點。座標、掃描半徑、輪詢間隔、OpenSky 憑證、鬧鐘喇叭都可以**直接在觸控螢幕上輸入**(也可透過網頁 / Home Assistant)。**時區**下拉(鬧鐘頁,每個城市附 UTC 偏移)與 **UNIT** 下拉(設定頁,METRIC/IMPERIAL 切換 °C/°F、km·h/mph、km/mi、m/ft、m·s/fpm 以及 RANGE 欄位本身;飛航高度層與節維持原樣)也在螢幕上設定。全部存於 NVS,重開機保留。
- **背光不可調光的板子改用夜間模式** — 微雪 Touch-LCD-5/5B 的背光接在 CH422G 擴充腳、無 PWM,只能開/關。那些板子上亮度滑桿改為控制全螢幕暗化遮罩,降低感知亮度並在重開機後保留。注意這不會降低耗電。
- **OTA 無線更新** — 第一次用 USB 燒錄後,之後都能無線更新。

### 硬體

| 零件 | 說明 |
|------|------|
| 主板 | ESP32-S3 5 吋 RGB 屏方案板(`esp32-s3-5inch-rgb-001`),8 MB PSRAM(octal)+ 16 MB flash |
| 面板 | 800×480 IPS,ST7262 RGB 驅動 |
| 觸控 | GT911 電容式(I²C) |
| 供電 | USB-C |
| 外殼 | 方案板 SDK 附 3D 列印外殼檔 |

### 支援的板子

| 入口 | 板子 | 主晶片 | 螢幕 | Wi-Fi | 狀態 |
|------|------|--------|------|-------|------|
| `radar.yaml` | esp32-s3-5inch-rgb-001(通用) | ESP32-S3 | 800×480 parallel-RGB(ST7262) | 原生 | **實機驗證過** |
| `radar-s3-5.yaml` | 微雪 ESP32-S3-Touch-LCD-5 | ESP32-S3 | 800×480 parallel-RGB(ST7262) | 原生 | config + 編譯驗證,**尚未實機燒錄** |
| `radar-s3-5b.yaml` | 微雪 ESP32-S3-Touch-LCD-5B | ESP32-S3 | 1024×600 parallel-RGB | 原生 | **實機驗證過** |
| `radar-p4-7b.yaml` | 微雪 ESP32-P4-WIFI6-Touch-LCD-7B | ESP32-P4 | 1024×600 MIPI-DSI(EK79007) | ESP32-C6(esp-hosted/SDIO) | **實機驗證過** —— 但 microSD 與截圖請用 `lvgl9` |

> **我該用哪個分支?** 兩個分支不是「舊」與「新」的關係,而是各自服務不同的板子,
> 兩邊都持續維護:
>
> | 板子 | 分支 | ESPHome | LVGL |
> |------|------|---------|------|
> | 三塊 **ESP32-S3** 板 | `main`(你在這裡) | 2026.3.3 | 8.4 |
> | **ESP32-P4** Touch-LCD-7B | `lvgl9` | 2026.6.5 | 9.5 |
>
> `radar-p4-7b.yaml` 在本分支可以編譯也能跑,但**沒有 microSD 支援、也沒有截圖** ——
> 兩者都需要只在新版 ESPHome 才載得起來的元件。手上是 P4 板請改用 `lvgl9` 分支。
> S3 留在這裡,是因為實測 LVGL 9 會讓掃描線變慢。

RGB 板共同需求:**≥8 MB octal PSRAM**(quad 餵不動 RGB 屏)、**GT911** I²C 觸控、16 MB flash
(`flash_size` 各板自訂)。其他白牌 800×480 RGB+GT911 板(Sunton ESP32-8048S050、Guition
JC8048W550…)照 `boards/esp32s3_rgb_800x480.yaml` 對腳位即可用 `radar.yaml`。

更多細節 —— 專案結構、逐板時序/腳位注意事項、本地元件覆寫,以及如何新增板子 ——
在 **[docs/BOARDS.md](docs/BOARDS.md)**。

### 軟體需求

- **建議 [ESPHome](https://esphome.io/) 2026.3.x**(`pip install esphome==2026.3.*`)。韌體直接呼叫 LVGL **v8** canvas 繪圖 API,故 **無法**在 2026.4.0+(改用 LVGL v9)編譯——見 issue #5。兩塊 1024×600 板另需 2025.9.0 才加入的 `mipi_rgb` / `mipi_dsi` 驅動,可用範圍為 **2025.9 – 2026.3**(2026.3.x 三塊板全涵蓋)。原始 800×480 `radar.yaml` 在任何 ≤2026.3.x 皆可。
- 相依的 `pngle` 會由 `platformio_options` 自動安裝。

### 燒錄

```bash
git clone https://github.com/delphicchen/esp32_flight_radar
cd esp32_flight_radar
esphome run radar.yaml          # ESP32-S3 800×480(原始板)
# 新面板改用:
# esphome run radar-s3-5.yaml   # 微雪 ESP32-S3-Touch-LCD-5(800×480)
# esphome run radar-s3-5b.yaml  # 微雪 ESP32-S3-Touch-LCD-5B(1024×600)
# esphome run radar-p4-7b.yaml  # 微雪 ESP32-P4-WIFI6-Touch-LCD-7B(1024×600)
```

第一次必須用 **USB** 燒錄(`/dev/ttyUSB0` 或 `/dev/ttyACM0`;Linux 上把自己加入 `dialout` 群組)。若燒錄卡住,按住 **BOOT**、點一下 **RESET**、放開 **BOOT** 進入下載模式。之後 `esphome run` 就能走 OTA 無線更新。

### 首次設定

1. 首次開機面板會開啟 Wi-Fi 熱點 **`Radar-Setup`**(密碼 `12345678`)。用手機連上,在跳出的設定頁選擇你家的 Wi-Fi。
2. *(只有選用 OpenSky 來源才需要)*註冊**免費的 OpenSky 帳號**,到帳號設定裡建立一個 **API Client**,取得 `client_id` 與 `client_secret`(OpenSky 使用 OAuth2,不是用你的登入密碼)。若改選 **airplanes.live** 或 **adsb.lol** 來源,完全不用註冊或金鑰。
3. 點螢幕右上角的 **Wi-Fi 圖示**或**底部狀態列**開啟網路 / API 設定頁,在螢幕上輸入 OpenSky 憑證。也可以在 `http://flight-radar.local` 或 Home Assistant 填寫。
4. 點**座標列**用數字鍵盤設定你的經緯度、掃描半徑與 OpenSky 輪詢秒數;**SRC** 列選擇資料來源(OPENSKY / A.LIVE / ADSB.LOL),**POLL2** 設定免費來源的輪詢秒數;並可勾選**背光關閉時是否持續抓取**(預設暫停)。選 OpenSky 時頁面會即時估算**每日 API credits 消耗**(以免費額度 4000/日 對照,綠/黃/紅顯示;半徑越大單次扣越多);免費來源無每日額度,但查詢半徑上限 250 海里(約 463 km)。
5. 約一分鐘內飛機就會出現。依喜好切換 **MAP** / **ECHO**。

### 設定項一覽

以下皆為 Home Assistant / 網頁實體,存於 NVS:

| 設定 | 意義 |
|------|------|
| OpenSky Client ID / Secret | OAuth2 API 憑證 |
| Home Latitude / Longitude | 雷達中心(你的位置) |
| Radar Range | 掃描半徑(公里,10–500) |
| Poll Interval | OpenSky 抓取間隔秒數(10–300,預設 30 → 每日 2880 次,在 4000 次/日額度內) |
| Poll Interval Alt | 免費來源(airplanes.live / adsb.lol)抓取間隔秒數(5–300,預設 15) |
| | 螢幕上只有一個 **POLL** 欄位 —— 它編輯的是目前 **ADS-B SRC** 對應的那一個,兩個值各自獨立保存。 |
| HA URL | 喇叭掃描用的 HA 位址(留空 = `http://homeassistant.local:8123`) |
| HA Token | SCAN 鈕使用的 HA 長期存取權杖 |
| Alarm Speaker | 預設發聲的 HA `media_player` 實體(手填或用 SCAN 選) |
| Alarm 1–4 Speaker | 各組鬧鐘的專屬喇叭;留空 = 用 Alarm Speaker |
| Alarm Sound URL | 鬧鐘響時播放的 mp3 |

### 延伸閱讀

- **[docs/USAGE.md](docs/USAGE.md)** —— 鬧鐘(含 Google Nest 喇叭)、ATC 模式、
  截圖存到 Home Assistant、在台灣以外地區使用
- **[docs/BOARDS.md](docs/BOARDS.md)** —— 板子接線、面板時序、元件覆寫,以及
  已在實機上排除的設定

### 資料來源與致謝

- 航班狀態 — [OpenSky Network](https://opensky-network.org/)、[airplanes.live](https://airplanes.live/)、[adsb.lol](https://adsb.lol/)
- 航線查詢 — [adsbdb.com](https://www.adsbdb.com/)
- 氣象雷達 — [RainViewer](https://www.rainviewer.com/)
- 在地天氣 — [Open-Meteo](https://open-meteo.com/)
- 台灣界線 — [g0v/twgeojson](https://github.com/g0v/twgeojson)
- 世界地圖資料 — [Natural Earth](https://www.naturalearthdata.com/)(public domain)
- 機場 / 跑道 / 導航台 — [OurAirports](https://ourairports.com/)(public domain)
- 台灣管制空域邊界 — [民航局 eAIP](https://ais.caa.gov.tw/) ENR 2.1
- 其他地區空域邊界(選用)— [openAIP](https://www.openaip.net/)(CC BY-NC)
- 概念啟發 — [AnthonySturdy/micro-radar](https://github.com/AnthonySturdy/micro-radar)
- 爬升/下降箭頭字型 — [DejaVu Sans](https://dejavu-fonts.github.io/)(Bitstream Vera / DejaVu 授權,`fonts/DejaVuSans.ttf`)

請遵守各資料來源的免費方案條款;本專案是自用興趣作品,並非商業服務。

---

## 🔗 Links / 友链

- 非常感谢 [LINUX DO](https://linux.do/latest) 社区提供的交流平台 / Many thanks to the LINUX DO community for the great discussion platform.

---

## 📄 License / 授權

**Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)**

You are free to **use, share and adapt** this project for **non-commercial purposes**, as long as you give appropriate credit and license your derivatives under the same terms. **Commercial use is not permitted.** See [`LICENSE`](LICENSE).

你可以基於**非商業目的**自由**使用、分享與改作**本專案,前提是註明出處並以相同條款授權你的衍生作品。**不允許商業使用。** 詳見 [`LICENSE`](LICENSE)。

© 2026 delphicchen
