# Usage guide / 使用指南

The features that need more than a sentence: alarms (including Google Nest
speakers), ATC mode, screenshots to Home Assistant, and using the radar outside
Taiwan.

需要多講幾句的功能:鬧鐘(含 Google Nest 喇叭)、ATC 模式、截圖存到 Home
Assistant,以及在台灣以外地區使用。

[English](#english) · [中文](#中文)

## English
## Alarm clock

- Tap the **clock** to open the alarm page (4 slots). For each: enable, tap the time to open a large scroll-wheel time picker, choose the weekdays, and (optionally) pick that alarm's own speaker from the dropdown at the end of its row.
- In the config fields set **Alarm Speaker** (a Home Assistant `media_player` entity, e.g. `media_player.living_room`) and optionally **Alarm Sound URL** (an mp3).
- In Home Assistant, open the device page and enable **"Allow the device to perform Home Assistant actions."** Otherwise the ESP32 cannot command the speaker.
- When an alarm fires, a **SNOOZE 9m / DISMISS** panel appears on screen. The sound **re-plays every 15 s until you press DISMISS**, so a short mp3 still keeps ringing.

### LOCAL SPEAKER (boards with onboard audio)

On boards that have an audio codec and a speaker header, the speaker dropdowns list **LOCAL SPEAKER** as the first entry. Pick it and the alarm beeps from the board itself — no Home Assistant, no token, no network involved. It is the only entry you get without an HA token.

The beep is a synthesised RTTTL tone (three short 1 kHz chirps per group, ~9 s, repeated every 15 s until DISMISS). To change the melody, edit the `rtttl.play` string in that board's file under `boards/`.

Which boards have it:

| Board | Onboard speaker |
|---|---|
| Waveshare ESP32-P4-WIFI6-Touch-LCD-7B | **Yes** — ES8311 codec + amplifier, MX1.25 speaker header |
| Waveshare ESP32-S3-Touch-LCD-5 / -7 | No audio hardware at all |
| Generic `esp32-s3-5inch-rgb-001` | Only the "audio" variant of the board has the codec fitted (base variant leaves those pins on the FPC header) |

Plug a small 4–8 Ω speaker into the header; USB power is enough for a beep.

> Playing an **mp3 from the microSD card** is *not* supported: ESPHome can play audio from an HTTP URL or from files baked into the firmware, but it has no SD-card media source. Ask if you want an alarm mp3 embedded in flash instead.

### Using a Google Nest / Chromecast speaker

1. Add the **Google Cast** integration in Home Assistant (it auto-discovers Nest/Cast devices on your LAN) → your speaker becomes a `media_player` entity.
2. In **Developer Tools → States** find its id (e.g. `media_player.nest_mini`) and put it in **Alarm Speaker**.
3. Cast devices only play a **full, reachable URL**. Put an mp3 in Home Assistant's `config/www/` and use `http://<HA-IP>:8123/local/alarm.mp3` (use the IP, not `homeassistant.local`).
4. Test first in **Developer Tools → Actions**: `media_player.play_media` with your entity and URL. If the speaker rings, the alarm will too.

### Speaker auto-discovery (SCAN button)

Instead of typing the entity id by hand, the alarm page can list every `media_player` in your Home Assistant. One-time setup:

1. In Home Assistant open your **profile (bottom-left avatar) → Security → Long-lived access tokens → Create token**. Copy it — it is shown only once.
2. Open the device's web page at `http://flight-radar.local` (or the device page in HA) and paste the token into **HA Token**. **HA URL** can stay empty — it defaults to `http://homeassistant.local:8123`; if the scan later reports `HA UNREACHABLE`, set it to your HA address by IP instead (e.g. `http://192.168.1.10:8123` — mDNS name resolution is unreliable on some networks). Both fields are saved to flash and survive reboots.
3. Open the alarm page — it **scans automatically** on entry once the token is set (or press **SCAN** in the top bar). All speaker dropdowns fill with friendly names: the **DEF** dropdown in the top bar is the default speaker (used by any alarm without its own), and each alarm row ends with that alarm's own dropdown. Picking a speaker saves immediately. Manual entry still works too (entities **Alarm Speaker** and **Alarm 1–4 Speaker**; leave an alarm's entry empty to use the default).

Troubleshooting: `SET HA TOKEN FIRST` = step 2 not done yet; `TOKEN INVALID` = the token is wrong or was revoked; `HA UNREACHABLE` = wrong HA URL / use the IP; `NO SPEAKERS FOUND` = HA has no `media_player` entities (add the Google Cast / Sonos / etc. integration first).

> **Security note:** a long-lived token grants full access to your Home Assistant and is stored in the device's flash. Treat it like a password and keep the device on a trusted network — the firmware only uses it for this read-only speaker query.

## ATC mode

Press the **ATC** button (in the top-right button row, between **ECHO** and **PWR**) to switch the radar from plane icons to an air-traffic-control style view; press again to instantly restore the default view.

- Each aircraft becomes a small **green target square**. Tap it exactly like the plane icon to select/deselect (same `select_slot` behavior).
- A thin line projects each aircraft's **position 2 minutes ahead** based on its current heading and ground speed.
- A **dotted fading trail** follows behind, through its last few fetched positions (dots, so it can't be confused with the solid vector line).
- Labels switch to two lines: callsign on top, `FL<flight level><climb arrow><speed>kts` below (`↑` climbing, `↓` descending, `=` level); the label auto-flips to the other side of the target when the velocity vector would run through it.
- **Conflict alert (red):** any two aircraft within **5.5 km** horizontally *and* **300 m** vertically both turn red; if one of them is the selected aircraft it blinks white/red instead of solid white.
- **Stale data (yellow):** if the data source hasn't updated an aircraft in over 60 s, its label turns yellow and gets a trailing `*`.
- Selected aircraft (no conflict) stay white.
- **Static video map:** ATC mode also bakes the `map_data.h` overlays into the base layer — airspace boundaries (CTR-class zones brighter blue, TMA/CTA dimmer), runways with **dashed extended centerlines**, airport squares with ICAO codes, and navaid/fix triangles with names. All of it disappears when ATC mode is switched off.
- **Layer panel:** the **SYS** button has two amber tabs — **SYSTEM** (hardware info + remaining OpenSky API quota, or the active free source when on airplanes.live / adsb.lol) and **ATC CONF**, where four toggles (**AIRSPACE / RUNWAY / AIRPORT / FIXES**) choose which map layers to draw (saved to NVS). The idle bottom-right panel keeps showing the local weather as usual.
- **Route line (ROUTE):** a fifth toggle in **ATC CONF**. When on, each label grows a third line with the flight's **origin–destination** (e.g. `KHH-KIX`), looked up per aircraft from [adsbdb.com](https://www.adsbdb.com/) in the background and cached, so each callsign is fetched only once. Lines appear as lookups complete (a few seconds); flights unknown to adsbdb simply show no third line. Saved to NVS like the other layer toggles.

## Screenshots to Home Assistant

Swipe **three fingers downward** anywhere on the screen to take a screenshot. The device snapshots the framebuffer, serves it at `http://flight-radar.local:8081/screenshot.bmp` (800×480 BMP) and fires the HA event `esphome.flight_radar_screenshot`. To save it automatically, add the **Downloader** integration in HA (set its directory, e.g. `/config/downloads`) and an automation:

```yaml
automation:
  - alias: Save flight radar screenshot
    trigger:
      - platform: event
        event_type: esphome.flight_radar_screenshot
    action:
      - service: downloader.download_file
        data:
          url: "http://flight-radar.local:8081/screenshot.bmp"
          filename: "radar_{{ now().strftime('%Y%m%d_%H%M%S') }}.bmp"
```

You can also just open the URL in a browser. If the colors come out wrong (red/blue swapped), set `SHOT_SWAP_BYTES` to `1` in `radar_fetch.h` and re-flash.

## Using it outside Taiwan

The repo ships with a Taiwan outline in `map_data.h`, but the radar projection itself is fully generic — just regenerate the map for your own location before compiling:

```bash
# Tokyo, up to 150 km range
python tools/make_map.py --lat 35.6762 --lon 139.6503 --radius 150

# London, 300 km, with state/province borders
python tools/make_map.py --lat 51.5074 --lon -0.1278 --radius 300 --states
```

The script (pure Python, no packages needed) downloads [Natural Earth](https://www.naturalearthdata.com/) 1:10m coastline + country border data (public domain, cached in `tools/cache/`), clips it around your coordinates, simplifies it to roughly one radar pixel of detail, and overwrites `map_data.h`. Set `--radius` to the largest radar range you plan to use. Useful options: `--states` adds admin-1 borders (can be dense in some countries), `--geojson file.geojson` uses your own boundary file instead of downloading, `--tol` / `--max-points` control detail. The three layers are drawn at different brightness — coastline brightest, country borders mid, state borders dimmest — so a busy map still reads at a glance; a `--geojson` file of your own is always drawn as the brightest layer.

The script also generates **ATC overlay data** (`AIRPORTS[]`, `RUNWAYS[]`, `FIXES[]`, `AIRSPACES[]`) into the same `map_data.h`. A complete run that produces everything at once:

```bash
# Taipei, 200 km: outline + airports & runways + navaids + 5-letter fixes + CTR/TMA airspaces
python tools/make_map.py --lat 25.03 --lon 121.56 --radius 200 \
    --countries TW --min-airport small --rwy-ext 15 \
    --fixes-csv my_fixes.csv --openaip-key YOURKEY
```

| Flag | What it does |
|------|--------------|
| `--countries TW` | restrict airports/navaids to these ISO country codes (omit = everything in range) |
| `--min-airport small` | also include small airfields (default `medium`; scheduled-service ones are always kept) |
| `--rwy-ext 15` | runway centerline extension in km (default 10) |
| `--fixes-csv my_fixes.csv` | add 5-letter AIP waypoints, one `NAME,lat,lon` per line |
| `--openaip-key YOURKEY` | fetch CTR/TMA/CTA airspaces from [openAIP](https://www.openaip.net/) (free account, data CC BY-NC); alternatively `--airspace-geojson file.geojson` (features need `name` + `type` properties), `--airspace-types` picks the classes |
| `--no-outline` | keep the `MAP_OUTLINE` already in the file (e.g. the stock g0v Taiwan outline), refresh overlays only |
| `--no-airports` / `--no-fixes` | skip those overlays entirely |

Airports, runways and navaids come from [OurAirports](https://ourairports.com/) open data (public domain, no key needed). Without an airspace source, `AIRSPACES[]` is simply empty. Note that openAIP coverage is community-maintained and varies a lot by region — Europe is dense, but **Taiwan has zero airspace data there**. For Taiwan the repo bundles `tools/taiwan_airspace.geojson` (FIR + 6 TMAs + 21 airport control zones), converted from the CAA eAIP ENR 2.1 with `tools/eaip_enr21_to_geojson.py` — that converter works on any IDS-AIRNAV-style eAIP ENR 2.1 page (handles coordinate lists, circles and arcs), so other un-covered countries can use the same route. The stock `map_data.h` was produced with:

```bash
python tools/make_map.py --lat 23.8 --lon 121.0 --radius 320 --countries TW --no-outline \
    --airspace-geojson tools/taiwan_airspace.geojson
```

## 中文
## 鬧鐘

- 點**時鐘**開啟鬧鐘頁(4 組)。每組:啟用、點時間彈出大型捲輪選擇器設定時 / 分、選擇星期幾,列尾的下拉選單可(選擇性)指定該組專屬喇叭。
- 在設定欄位填入 **Alarm Speaker**(Home Assistant 的 `media_player` 實體,例如 `media_player.living_room`),以及可選的 **Alarm Sound URL**(mp3)。
- 在 Home Assistant 的裝置頁開啟「**允許此裝置執行 Home Assistant 動作**」,否則 ESP32 無法命令喇叭。
- 鬧鐘響時,螢幕會出現 **SNOOZE 9m / DISMISS** 面板。聲音會**每 15 秒重播一次,直到你按下 DISMISS**,所以短音檔也能持續響。

### LOCAL SPEAKER(板載喇叭的板子)

板子上有音訊 codec 與喇叭座時,喇叭下拉選單的第一項會是 **LOCAL SPEAKER**。選它,鬧鐘就由板子自己發聲——不經 Home Assistant、不用權杖、不用網路。沒填 HA Token 時,清單裡也只有這一項。

聲音是 RTTTL 合成音(每組三聲約 1 kHz 短鳴,約 9 秒,每 15 秒重播直到 DISMISS)。想換旋律直接改該板子 `boards/` 檔案裡的 `rtttl.play` 字串。

哪些板子有:

| 板子 | 板載喇叭 |
|---|---|
| Waveshare ESP32-P4-WIFI6-Touch-LCD-7B | **有** —— ES8311 codec + 功放,MX1.25 喇叭座 |
| Waveshare ESP32-S3-Touch-LCD-5 / -7 | 完全沒有音訊硬體 |
| 通用 `esp32-s3-5inch-rgb-001` | 只有「集成音頻播放款」焊了 codec(基礎款那幾支腳留在 FPC 排針上) |

喇叭座接一顆 4–8 Ω 小喇叭即可,USB 供電足夠發出提示音。

> **不支援**從 microSD 播 mp3:ESPHome 能播 HTTP URL 或燒進韌體的音檔,但沒有 SD 卡的媒體來源。若想把鬧鈴 mp3 包進 flash,跟我說。

### 使用 Google Nest / Chromecast 喇叭

1. 在 Home Assistant 新增 **Google Cast** 整合(會自動發現區網內的 Nest / Cast 裝置)→ 喇叭變成一個 `media_player` 實體。
2. 到 **開發者工具 → 狀態** 找出它的 id(例如 `media_player.nest_mini`),填進 **Alarm Speaker**。
3. Cast 裝置只吃**完整、連得到的 URL**。把 mp3 放到 HA 的 `config/www/`,網址用 `http://<HA的IP>:8123/local/alarm.mp3`(用 IP,不要用 `homeassistant.local`)。
4. 先在 **開發者工具 → 動作** 用 `media_player.play_media` 帶入你的實體與網址測試;喇叭有響,鬧鐘就會響。

### 自動搜尋喇叭(SCAN 鈕)

不必手打 entity id,鬧鐘頁可以直接列出 HA 裡所有的 `media_player`。一次性設定:

1. 在 Home Assistant 開啟**個人資料(左下角頭像)→ 安全性 → 長期存取權杖 → 建立權杖**,複製起來——它只會顯示這一次。
2. 開啟裝置網頁 `http://flight-radar.local`(或 HA 的裝置頁),把權杖貼進 **HA Token**。**HA URL** 可以留空——預設 `http://homeassistant.local:8123`;若之後掃描顯示 `HA UNREACHABLE`,請改填 HA 的 IP(如 `http://192.168.1.10:8123`,mDNS 名稱解析在部分網路不可靠)。兩個欄位都會存進 flash,重開機不會消失。
3. 開啟鬧鐘頁——權杖填好後**進頁會自動掃描**(也可按頂列的 **SCAN**)。所有喇叭下拉選單會列出友善名稱:頂列 **DEF** 選單是預設喇叭(沒有專屬喇叭的鬧鐘用它),每組鬧鐘列尾則是該組的專屬選單。挑了就立即存檔。仍然可以手動填寫(實體 **Alarm Speaker** 與 **Alarm 1–4 Speaker**;某組留空 = 用預設)。

疑難排解:`SET HA TOKEN FIRST` = 還沒做第 2 步;`TOKEN INVALID` = 權杖錯誤或已撤銷;`HA UNREACHABLE` = HA URL 不對,改用 IP;`NO SPEAKERS FOUND` = HA 裡沒有任何 `media_player` 實體(先新增 Google Cast / Sonos 等整合)。

> **安全性提醒:**長期權杖等同 HA 的完整存取權,且儲存在裝置 flash 中。請把它當密碼看待、讓裝置留在信任的內網;韌體只會用它做這個唯讀的喇叭查詢。

## ATC 模式

按右上角按鈕列的 **ATC** 鈕(在 **ECHO** 與 **PWR** 之間)切換成航管風格畫面;再按一次立即還原成預設的飛機圖示畫面。

- 每架飛機變成一個小小的**綠色目標方塊**,點擊方式跟飛機圖示一樣(照樣呼叫 `select_slot` 選取/取消選取)。
- 一條細線依目前航向與地速,投射該機**2 分鐘後的推算位置**。
- **點線漸淡軌跡**跟在機後,連向最近幾次抓取到的舊位置(點狀,不會與實線向量混淆)。
- 標籤改成兩行:第一行呼號,第二行 `FL高度層+爬升箭頭+速度kts`(`↑` 爬升、`↓` 下降、`=` 平飛);向量線會穿過標籤時,標籤自動翻到目標另一側。
- **衝突告警(紅色)**:任兩機水平距離 < **5.5 km** 且高度差 < **300 m** 時雙雙變紅;若其中一台是目前選取的飛機,改成白/紅交替閃爍而非純白。
- **資料延遲(黃色)**:資料來源超過 60 秒沒更新該機資料,標籤變黃並在呼號後加 `*`。
- 選取中且無衝突的飛機維持白色。
- **靜態航圖(video map)**:ATC 模式同時把 `map_data.h` 的圖層烤進底圖——管制空域邊界(CTR 類亮藍、TMA/CTA 暗藍)、跑道與**虛線延伸中線**、機場方塊+ICAO 代碼、導航點三角+名稱。關閉 ATC 模式即全部消失。
- **圖層面板**:**SYS** 鈕內有兩個 amber 色分頁——**SYSTEM**(硬體資訊+OpenSky API 當日剩餘額度;用免費來源時改顯示目前來源)與 **ATC CONF**,後者的四個開關(**AIRSPACE / RUNWAY / AIRPORT / FIXES**)設定要畫哪些航圖圖層(存 NVS)。右下閒置畫面維持顯示在地天氣,跟原本一樣。
- **起訖站行(ROUTE)**:**ATC CONF** 的第五個開關。開啟後每個標籤多出第三行**起訖機場**(例 `KHH-KIX`),逐架在背景向 [adsbdb.com](https://www.adsbdb.com/) 查詢並快取,同一呼號只查一次;查詢完成後幾秒內陸續浮現,adsbdb 查無資料的航班就不顯示第三行。與其他圖層開關一樣存 NVS。

## 截圖存到 Home Assistant

在螢幕任意處**三指下滑**即截圖。裝置會快照 framebuffer、在 `http://flight-radar.local:8081/screenshot.bmp` 提供 800×480 BMP,並發出 HA 事件 `esphome.flight_radar_screenshot`。要自動存檔的話,在 HA 加入 **Downloader** 整合(設定下載目錄,例如 `/config/downloads`)並建立自動化:

```yaml
automation:
  - alias: 存雷達截圖
    trigger:
      - platform: event
        event_type: esphome.flight_radar_screenshot
    action:
      - service: downloader.download_file
        data:
          url: "http://flight-radar.local:8081/screenshot.bmp"
          filename: "radar_{{ now().strftime('%Y%m%d_%H%M%S') }}.bmp"
```

也可以直接用瀏覽器開那個網址。若截圖顏色不對(紅藍對調),把 `radar_fetch.h` 的 `SHOT_SWAP_BYTES` 改成 `1` 重新燒錄。

## 在台灣以外地區使用

repo 內附的 `map_data.h` 是台灣輪廓,但雷達投影本身完全通用——編譯前為你的位置重新產生地圖即可:

```bash
# 東京,最大半徑 150 km
python tools/make_map.py --lat 35.6762 --lon 139.6503 --radius 150

# 倫敦,300 km,加省/州界
python tools/make_map.py --lat 51.5074 --lon -0.1278 --radius 300 --states
```

腳本(純 Python,免裝套件)會下載 [Natural Earth](https://www.naturalearthdata.com/) 1:10m 海岸線+國界資料(public domain,快取於 `tools/cache/`),裁切你座標周圍的範圍、簡化到約一個雷達像素的細節,然後覆寫 `map_data.h`。`--radius` 請設為你會用到的最大雷達半徑。常用選項:`--states` 加省/州界(部分國家會很密)、`--geojson file.geojson` 改用自備邊界檔不下載、`--tol` / `--max-points` 調細節。三種圖層會以不同亮度繪製——海岸線最亮、國界次之、州/省界最暗——線一多也還分得出主次;自備的 `--geojson` 邊界檔一律畫成最亮的那層。

腳本同時會產生 **ATC 圖層資料**(`AIRPORTS[]`、`RUNWAYS[]`、`FIXES[]`、`AIRSPACES[]`)到同一個 `map_data.h`。一次產生全部資訊的完整範例:

```bash
# 台北 200 km:輪廓 + 機場/跑道 + 導航台 + 5 碼航點 + CTR/TMA 空域
python tools/make_map.py --lat 25.03 --lon 121.56 --radius 200 \
    --countries TW --min-airport small --rwy-ext 15 \
    --fixes-csv my_fixes.csv --openaip-key YOURKEY
```

| 選項 | 作用 |
|------|------|
| `--countries TW` | 機場/導航台只保留這些 ISO 國碼(不給 = 範圍內全部) |
| `--min-airport small` | 連小型機場也納入(預設 `medium`;有定期航班的一律保留) |
| `--rwy-ext 15` | 跑道中線延伸公里數(預設 10) |
| `--fixes-csv my_fixes.csv` | 匯入 AIP 的 5 碼航點,每行 `NAME,lat,lon` |
| `--openaip-key YOURKEY` | 從 [openAIP](https://www.openaip.net/) 抓 CTR/TMA/CTA 空域(免費註冊;資料授權 CC BY-NC);也可改用 `--airspace-geojson file.geojson`(feature 需有 `name`+`type` 屬性),`--airspace-types` 選類別 |
| `--no-outline` | 保留檔內既有的 `MAP_OUTLINE`(例如內附的 g0v 台灣輪廓),只更新圖層陣列 |
| `--no-airports` / `--no-fixes` | 完全跳過該圖層 |

機場、跑道、導航台資料來自 [OurAirports](https://ourairports.com/) 開放資料(public domain,免金鑰)。沒給空域來源時 `AIRSPACES[]` 就是空的。注意 openAIP 是社群維護、各地覆蓋差很多——歐洲很完整,但**台灣完全沒有空域資料**。台灣空域 repo 已內附 `tools/taiwan_airspace.geojson`(FIR + 6 個 TMA + 21 個機場管制空域),由 `tools/eaip_enr21_to_geojson.py` 從民航局 eAIP ENR 2.1 轉出——這個轉換器支援座標點列、圓、圓弧三種幾何,任何 IDS AIRNAV 系統的 eAIP 都適用,其他 openAIP 沒覆蓋的國家可走同樣路線。內附的 `map_data.h` 由這個指令產生:

```bash
python tools/make_map.py --lat 23.8 --lon 121.0 --radius 320 --countries TW --no-outline \
    --airspace-geojson tools/taiwan_airspace.geojson
```
