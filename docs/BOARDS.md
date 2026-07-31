# Boards & internals / 板子與內部細節

Per-board wiring, panel timings, the local ESPHome component overrides and the
dead ends already ruled out on hardware. Read this before adding a board or
changing a display setting.

逐板接線、面板時序、本地 ESPHome 元件覆寫,以及已經在實機上排除掉的死路。
新增板子或調整顯示設定前請先看這份。

[English](#english) · [中文](#中文)

## English
### Supported boards & project structure

The firmware is split into **reusable packages** so a new display board is just a
new board file plus a matching layout — the shared logic never changes:

```
radar.yaml            entry: ESP32-S3 + 800×480 RGB   (the original board)
radar-s3-5.yaml       entry: Waveshare ESP32-S3-Touch-LCD-5   (800×480 RGB)
radar-s3-5b.yaml      entry: Waveshare ESP32-S3-Touch-LCD-5B  (1024×600 RGB)
radar-p4-7b.yaml      entry: Waveshare ESP32-P4-WIFI6-Touch-LCD-7B (1024×600 MIPI-DSI)
common/core.yaml      shared logic + UI-independent components (fonts, scripts, …)
boards/*.yaml         per-board hardware: MCU / PSRAM / display / touch / backlight
components/*          local overrides of two ESPHome components, pulled in by the
                      Waveshare board files (see "Local component overrides")
ui/ui_800x480.yaml    LVGL layout at 800×480  ← edit this one
ui/ui_1024x600.yaml   LVGL layout at 1024×600  (generated; re-run tools/scale_layout.py)
```

Each entry file just picks a resolution (via `substitutions`) and a `board` + `ui`
package. Screen size flows into the fonts, the display driver and the C++ helpers
(through `build_flags` → `radar_fetch.h` macros), so there are no hard-coded
dimensions left to chase.

| Entry | Board | MCU | Panel | Wi-Fi | Status |
|-------|-------|-----|-------|-------|--------|
| `radar.yaml` | esp32-s3-5inch-rgb-001 (generic) | ESP32-S3 | 800×480 parallel-RGB (ST7262) | native | **verified on hardware** |
| `radar-s3-5.yaml` | Waveshare ESP32-S3-Touch-LCD-5 | ESP32-S3 | 800×480 parallel-RGB (ST7262) | native | config + build verified, **not yet flashed** |
| `radar-s3-5b.yaml` | Waveshare ESP32-S3-Touch-LCD-5B | ESP32-S3 | 1024×600 parallel-RGB | native | **verified on hardware** |
| `radar-p4-7b.yaml` | Waveshare ESP32-P4-WIFI6-Touch-LCD-7B | ESP32-P4 | 1024×600 MIPI-DSI (EK79007) | ESP32-C6 (esp-hosted/SDIO) | **verified on hardware** (panel, colours, touch) |

Common requirements for the RGB boards: **≥8 MB octal PSRAM** (quad-PSRAM can't feed
the RGB panel), a **GT911** I²C touch controller, and 16 MB flash (`flash_size` is set
per board). Other generic 800×480 RGB+GT911 boards (Sunton ESP32-8048S050, Guition
JC8048W550, …) work with `radar.yaml` after matching the pins in
`boards/esp32s3_rgb_800x480.yaml`.

**Adding a board:** drop a new file in `boards/`, set its pins/driver, then copy an
entry file and point `board:`/`ui:` at it. For a new resolution, regenerate a layout
with `python3 tools/scale_layout.py ui/ui_800x480.yaml ui/ui_<w>x<h>.yaml <factor>`
and set `radar_canvas`/font sizes to match. **`ui/ui_800x480.yaml` is the source of
truth** — the other layouts are generated, so edit the 800×480 file and re-run the
script instead of touching the generated one.

### Local component overrides

The two Waveshare board files pull in `components/` via `external_components`. Each is a
copy of an upstream ESPHome component with exactly one change, marked by a comment in the
file:

| Override | Why |
|----------|-----|
| `components/psram` | For octal + 120 MHz on IDF ≥ 5.4, ESPHome unconditionally enables `CONFIG_SPIRAM_TIMING_TUNING_POINT_VIA_TEMPERATURE_SENSOR`. IDF's implementation only accepts flash vendor IDs `0xC8`/`0x20` and aborts with `0x106` otherwise, so these boards boot-loop. The option cannot be pushed back to `n` through `sdkconfig_options` — psram's `to_code` runs last and always wins — hence the component copy. |

There used to be a second override, `components/lvgl`, which moved the LVGL draw buffer
from PSRAM into internal SRAM (rendering otherwise competes with the RGB panel's scanout
DMA for the same bus, which shows up as UI stalls of several hundred ms and as flicker).
ESPHome 2026.4+ does this itself — it asks for internal memory first and falls back to
PSRAM — so on this branch the override is gone. What is lost with it is the ability to
halve the buffer again: upstream quantises `buffer_size` to 1/1, 1/2, 1/4 or 1/8, and on
the 5B a 1/8 (154 KB) internal buffer previously starved mbedTLS. Watch the boot log.

The psram override can go once upstream ESPHome handles that case: delete the directory
and the matching `external_components` block to fall back to the built-in component.

> **Status of the Waveshare boards.** The **5B (1024×600)** has been flashed and tuned
> on real hardware — panel timings, PSRAM speed, draw-buffer placement and the backlight
> behaviour below all come from measurements on that unit. The **5 (800×480)** shares the
> same PCB and pin map (Waveshare switch the two with one macro in
> `waveshare_lcd_port.h`); its porches and pixel clock are copied verbatim from their
> example code, but it is config- and build-verified only — no 800×480 panel here.
> The **P4-7B** has now been flashed and its panel, colours and touch verified. Three
> things had to be right at once, and they interact:
> `byte_order` must match between the display and the `lvgl` block (both `little_endian`
> here — the display default; leaving LVGL on its own `big_endian` default swaps every
> RGB565 byte pair and tints the whole screen dark red), the panel scans 180° from the UI
> so the display needs `rotation: 180°` (this model is `no_transform`, so LVGL does it in
> software and allocates a second rotation buffer), and the GT911 needs **no** transform —
> its origin already matches the panel. Note the SDIO bus to the C6 is *not* the microSD
> SDMMC bus: the official `04_sdmmc` example uses CLK 43 / CMD 44 / D0-D3 39,40,41,42
> for the card, which are different pins. On the P4 the parallel-RGB framebuffer
> screenshot is compiled out (MIPI-DSI has no equivalent grab); every other feature is
> shared. Wi-Fi over the C6 has not been confirmed working yet.
>
> **Take pin numbers from the official BSP, not from the P4 family in general.** The
> component-registry BSP `waveshare/esp32_p4_wifi6_touch_lcd_7b`
> (`include/bsp/esp32_p4_wifi6_touch_lcd_7b.h`) is authoritative for this board:
> backlight **GPIO32** (LEDC PWM, active-low), panel reset GPIO33, I²C 7/8, I2S
> MCLK 13 / BCLK 12 / LRCK 10 / DOUT 9 with the amplifier enable on **GPIO53**, SD over
> SDMMC 43/44/39-42. An earlier guess of GPIO26 for the backlight left both the PWR
> button and the brightness slider doing nothing. The ES8311 codec on that I2S bus is
> what gives this board the **LOCAL SPEAKER** alarm target (`-DRADAR_LOCAL_SPK=1`).
>
> **Do not raise `pclk_frequency` above what the board file sets.** Waveshare run this
> panel family at 16 MHz. Pushing the 1024×600 board to 40 MHz produced a permanent
> horizontal offset, and 52 MHz tore the image outright. If the picture flickers, the
> cause is almost certainly PSRAM bandwidth rather than refresh rate — see the LVGL
> draw-buffer note below.

## 中文
### 支援的板子與專案結構

韌體已拆成**可重用的 packages**,新增一塊螢幕只要加一個 board 檔加一份對應版面,共用邏輯完全不動:

```
radar.yaml            入口:ESP32-S3 + 800×480 RGB(原始板)
radar-s3-5.yaml       入口:微雪 ESP32-S3-Touch-LCD-5(800×480 RGB)
radar-s3-5b.yaml      入口:微雪 ESP32-S3-Touch-LCD-5B(1024×600 RGB)
radar-p4-7b.yaml      入口:微雪 ESP32-P4-WIFI6-Touch-LCD-7B(1024×600 MIPI-DSI)
common/core.yaml      共用邏輯 + 與版面無關的元件(字型、腳本…)
boards/*.yaml         各板硬體:MCU / PSRAM / 螢幕 / 觸控 / 背光
components/*          兩個 ESPHome 元件的本地覆寫,由微雪板檔載入(見「本地元件覆寫」)
ui/ui_800x480.yaml    800×480 的 LVGL 版面 ← 改這一份
ui/ui_1024x600.yaml   1024×600 版面(生成檔;改完來源要重跑 tools/scale_layout.py)
```

入口檔只用 `substitutions` 選解析度,再挑 `board` + `ui` 兩個 package。解析度會流進字型、
display 驅動與 C++ 巨集(透過 `build_flags` → `radar_fetch.h`),不再有寫死的尺寸。

| 入口 | 板子 | 主晶片 | 螢幕 | Wi-Fi | 狀態 |
|------|------|--------|------|-------|------|
| `radar.yaml` | esp32-s3-5inch-rgb-001(通用) | ESP32-S3 | 800×480 parallel-RGB(ST7262) | 原生 | **實機驗證過** |
| `radar-s3-5.yaml` | 微雪 ESP32-S3-Touch-LCD-5 | ESP32-S3 | 800×480 parallel-RGB(ST7262) | 原生 | config + 編譯驗證,**尚未實機燒錄** |
| `radar-s3-5b.yaml` | 微雪 ESP32-S3-Touch-LCD-5B | ESP32-S3 | 1024×600 parallel-RGB | 原生 | **實機驗證過** |
| `radar-p4-7b.yaml` | 微雪 ESP32-P4-WIFI6-Touch-LCD-7B | ESP32-P4 | 1024×600 MIPI-DSI(EK79007) | ESP32-C6(esp-hosted/SDIO) | **實機驗證過**(面板、顏色、觸控) |

RGB 板共同需求:**≥8 MB octal PSRAM**(quad 餵不動 RGB 屏)、**GT911** I²C 觸控、16 MB flash
(`flash_size` 各板自訂)。其他白牌 800×480 RGB+GT911 板(Sunton ESP32-8048S050、Guition
JC8048W550…)照 `boards/esp32s3_rgb_800x480.yaml` 對腳位即可用 `radar.yaml`。

**新增板子:**在 `boards/` 放一個新檔設定腳位/驅動,再複製一個入口檔把 `board:`/`ui:` 指過去。
換新解析度時用 `python3 tools/scale_layout.py ui/ui_800x480.yaml ui/ui_<w>x<h>.yaml <倍率>`
生成版面,並把 `radar_canvas`/字型大小對應調整。**`ui/ui_800x480.yaml` 是唯一來源** ——
其他解析度的版面都是生成檔,要改請改 800×480 那份再重跑腳本,不要動生成檔。

### 本地元件覆寫

兩塊微雪板檔會透過 `external_components` 載入 `components/`。每個都是上游 ESPHome 元件的
複本、只改一處,檔案裡都有註解標明改動點:

| 覆寫 | 原因 |
|------|------|
| `components/psram` | octal + 120 MHz 且 IDF ≥ 5.4 時,ESPHome 會無條件開啟 `CONFIG_SPIRAM_TIMING_TUNING_POINT_VIA_TEMPERATURE_SENSOR`。IDF 的實作只接受 flash 廠商 ID `0xC8`/`0x20`,其他一律回 `0x106` 並 abort,於是這些板子開機就無限重啟。這個選項無法用 `sdkconfig_options` 壓回 `n`(psram 的 `to_code` 最後執行、必定覆蓋),只能整個覆寫元件。 |

原本還有第二個覆寫 `components/lvgl`,作用是把 LVGL 繪圖緩衝從 PSRAM 移到內部 SRAM
(否則渲染會和 RGB 面板的掃描 DMA 搶同一條匯流排,表現為數百 ms 的 UI 卡頓與閃爍)。
ESPHome 2026.4+ 已內建這個行為(先要內部記憶體、失敗才退回 PSRAM),所以這個分支把覆寫
刪掉了。代價是不能再把緩衝減半:上游把 `buffer_size` 量化成 1/1、1/2、1/4、1/8,而 5B 上
1/8(154KB)的內部緩衝曾經餓死 mbedTLS,請留意開機 log。

psram 覆寫則要等上游修好才能刪:移除該目錄與對應的 `external_components` 區塊即可回到
內建元件。

> **微雪各板的狀態。5B(1024×600)** 已在實機上燒錄並調校 —— 面板時序、PSRAM 速度、繪圖
> 緩衝位置與下面的背光行為,全部來自那台機器的實測。**5(800×480)** 與 5B 是同一片 PCB、
> 同一組腳位(微雪用 `waveshare_lcd_port.h` 裡一個巨集切換兩者),porch 與 pixel clock 直接
> 照抄官方範例,但只做過 config 與編譯驗證 —— 手上沒有 800×480 面板。
> **P4-7B 已實機燒錄**,面板、顏色、觸控都驗證過。有三件事必須同時正確,而且互相牽動:
> `byte_order` 要與 `lvgl` 區塊一致(這裡兩邊都是 `little_endian`,即 display 的預設值;
> 若讓 LVGL 留在它自己的 `big_endian` 預設,每個 RGB565 的位元組對會被交換,整片畫面偏
> 暗紅)、面板掃描方向與 UI 差 180 度所以 display 要 `rotation: 180°`(這個 model 標了
> `no_transform`,只能由 LVGL 軟體旋轉並另配一份旋轉緩衝)、而 GT911 **不要**任何
> transform —— 它的原點本來就與面板一致。注意連到 C6 的 SDIO **不是** microSD 的 SDMMC:
> 官方 `04_sdmmc` 範例給 TF 卡用的是 CLK 43 / CMD 44 / D0-D3 39,40,41,42,是另一組腳位。
> P4 上平行 RGB 的 framebuffer 截圖會被編譯掉(DSI 無對應的抓取方式),其餘功能完全共用。
> 透過 C6 的 Wi-Fi 目前尚未確認可用。
>
> **腳位要查這片板子的官方 BSP,不要用 P4 家族的通例去推。** 元件登錄庫的
> `waveshare/esp32_p4_wifi6_touch_lcd_7b`(`include/bsp/esp32_p4_wifi6_touch_lcd_7b.h`)
> 才是這片板子的權威:背光 **GPIO32**(LEDC PWM、低電位點亮)、面板 reset GPIO33、
> I²C 7/8、I2S MCLK 13 / BCLK 12 / LRCK 10 / DOUT 9,功放致能在 **GPIO53**,
> SD 走 SDMMC 43/44/39-42。先前把背光猜成 GPIO26,結果 PWR 鈕與亮度滑桿都沒反應。
> 那條 I2S 上的 ES8311 codec 就是這片板子能有 **LOCAL SPEAKER** 鬧鐘目標的原因
> (`-DRADAR_LOCAL_SPK=1`)。
>
> **不要把 `pclk_frequency` 調到高於板檔的設定值。** 微雪這個面板家族官方跑 16 MHz。
> 1024×600 板拉到 40 MHz 會出現固定的水平偏移,52 MHz 則整幅撕裂。畫面若閃爍,幾乎一定是
> PSRAM 頻寬而非刷新率不足 —— 見下方 LVGL 繪圖緩衝的說明。
