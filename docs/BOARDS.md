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

### Gotcha: flashing the wrong board's image

All four entry files use the same ESPHome `name: flight-radar`, and ESPHome caches the
build's file paths in **`.esphome/idedata/flight-radar.json`, keyed on that name alone**.
So after you compile one board, an `esphome run` for a *different* board compiles into the
right directory but then reads the **previous board's** firmware path out of that cache and
tries to flash it. The cache is only refreshed when the current build's `platformio.ini` is
newer than it, which is not the case when you switch back and forth.

The symptom is unmistakable — esptool refuses the image rather than bricking anything:

```
Warning: Unexpected chip ID in image. Expected 18 but value was 9.
ERROR ... firmware.bin' is not an an ESP32-P4 image.
```

(chip id 18 = ESP32-P4, 9 = ESP32-S3). The fix is to drop the stale cache; it is rebuilt
automatically on the next run:

```bash
rm .esphome/idedata/flight-radar.json
```

Giving each board its own build directory (`ESPHOME_BUILD_PATH=build9 esphome run
radar-p4-7b.yaml`) keeps the *object files* separate and is still worth doing, but it does
not avoid this — the idedata cache sits above the build path. If you would rather bypass
ESPHome entirely, flash a factory image straight from `dist/` with esptool:

```bash
esptool --chip esp32p4 --port /dev/ttyACM0 --baud 460800 \
  write-flash -z --flash-size detect 0x0 dist/flight-radar-<board>-<version>.factory.bin
```

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
PSRAM — so that part of the override is gone. What upstream cannot do is go below 1/8 of
the screen: `buffer_size` is quantised to 1/1, 1/2, 1/4 or 1/8, and on the 5B a 1/8
(154 KB) internal buffer starves mbedTLS (`alloc(4770 bytes) failed`, handshakes return
`-0x7F00`). Moving TLS to PSRAM only moves the problem — the AES accelerator then fails to
allocate its internal DMA bounce buffer (`esp-aes: Failed to allocate memory`). So the
override survives, reduced to one change: halve the buffer once more (1/16 = 77 KB) and
insist on `MALLOC_CAP_INTERNAL`.

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
> so it needs `rotation: 180°` — on this branch that goes in the **`lvgl:`** block, not
> `display:`, which LVGL 9 rejects outright (this model is `no_transform`, so LVGL does
> it in software and allocates a second rotation buffer).
>
> That rotation has two consequences that are easy to miss, because they pull in
> opposite directions. The LVGL component rotates **pointer input** by the same angle,
> while ESPHome's touchscreen base never looks at rotation at all — so the GT911, whose
> raw origin already matches the UI, needs `mirror_x` + `mirror_y` to cancel LVGL's
> flip. But the three-finger gesture handler reads the touchscreen's own coordinates,
> which do *not* pass through LVGL, so it sees the mirrored values and its comparison
> has to invert with them. Change one and you must change the other.
>
> **microSD works on this branch.** The card is on the native SDMMC bus — CLK 43 /
> CMD 44 / D0-D3 39,40,41,42, slot 0, which does not collide with the C6's SDIO on
> slot 1. Two things are not obvious: the P4 powers the card's IO rail from an on-chip
> LDO that nothing turns on by default (patched into the vendored `sd_storage`, channel
> 4, matching Espressif's own P4 BSP), and the card must be **FAT32** — exFAT and NTFS
> are not compiled in, and an NTFS card fails in a thoroughly misleading way: it mounts
> far enough to read sector 0, then FATFS treats the NTFS boot code as a partition table
> and reads past the end of the card.
>
> **Screenshots work too**, reading the DPI framebuffer back with
> `esp_lcd_dpi_panel_get_frame_buffer()`. Two board flags go with it: `SHOT_SWAP_BYTES=0`
> because this framebuffer is native RGB565 rather than byte-swapped, and
> `RADAR_SHOT_ROT180=1` because LVGL rotates the UI *before* it reaches the framebuffer,
> so what you see upright is stored upside down. Wi-Fi over the C6 is confirmed working.
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

### 陷阱:燒到另一塊板的映像

四個入口檔的 ESPHome `name:` 都是 `flight-radar`,而 ESPHome 會把建置產物的路徑快取在
**`.esphome/idedata/flight-radar.json`,而且 key 只用這個 name**。所以你編過一塊板之後,
再對*另一塊*板下 `esphome run`,編譯會進到正確的目錄,但上傳階段會從那份快取讀出
**前一塊板的** firmware 路徑並試圖燒進去。快取只在「當前建置的 `platformio.ini` 比它新」
時才更新,而來回切換板子時通常不會。

症狀很好認 —— esptool 會擋下來,不會真的燒壞:

```
Warning: Unexpected chip ID in image. Expected 18 but value was 9.
ERROR ... firmware.bin' is not an an ESP32-P4 image.
```

(chip id 18 = ESP32-P4、9 = ESP32-S3)。解法是把過期快取刪掉,下次執行會自動重建:

```bash
rm .esphome/idedata/flight-radar.json
```

給每塊板各自的建置目錄(`ESPHOME_BUILD_PATH=build9 esphome run radar-p4-7b.yaml`)可以
讓*目的檔*不互相覆蓋,仍然值得做,但**擋不住這個問題** —— idedata 快取在 build path 之上。
想完全繞開 ESPHome 的話,直接用 esptool 燒 `dist/` 裡的 factory 映像:

```bash
esptool --chip esp32p4 --port /dev/ttyACM0 --baud 460800 \
  write-flash -z --flash-size detect 0x0 dist/flight-radar-<板子>-<版本>.factory.bin
```

### 本地元件覆寫

兩塊微雪板檔會透過 `external_components` 載入 `components/`。每個都是上游 ESPHome 元件的
複本、只改一處,檔案裡都有註解標明改動點:

| 覆寫 | 原因 |
|------|------|
| `components/psram` | octal + 120 MHz 且 IDF ≥ 5.4 時,ESPHome 會無條件開啟 `CONFIG_SPIRAM_TIMING_TUNING_POINT_VIA_TEMPERATURE_SENSOR`。IDF 的實作只接受 flash 廠商 ID `0xC8`/`0x20`,其他一律回 `0x106` 並 abort,於是這些板子開機就無限重啟。這個選項無法用 `sdkconfig_options` 壓回 `n`(psram 的 `to_code` 最後執行、必定覆蓋),只能整個覆寫元件。 |

原本還有第二個覆寫 `components/lvgl`,作用是把 LVGL 繪圖緩衝從 PSRAM 移到內部 SRAM
(否則渲染會和 RGB 面板的掃描 DMA 搶同一條匯流排,表現為數百 ms 的 UI 卡頓與閃爍)。
ESPHome 2026.4+ 已內建這個行為(先要內部記憶體、失敗才退回 PSRAM),所以這個分支把覆寫
刪掉了這部分。上游做不到的是「小於 1/8 螢幕」:`buffer_size` 被量化成 1/1、1/2、1/4、1/8,
而 5B 上 1/8(154KB)的內部緩衝會餓死 mbedTLS(`alloc(4770 bytes) failed`、握手 `-0x7F00`)。
把 TLS 改配 PSRAM 只是把問題往下推——換成 AES 加速器配不到內部 DMA 跳板緩衝
(`esp-aes: Failed to allocate memory`)。所以覆寫仍在,只精簡成一件事:再減半一次
(1/16 = 77KB)並明確要求 `MALLOC_CAP_INTERNAL`。

psram 覆寫則要等上游修好才能刪:移除該目錄與對應的 `external_components` 區塊即可回到
內建元件。

> **微雪各板的狀態。5B(1024×600)** 已在實機上燒錄並調校 —— 面板時序、PSRAM 速度、繪圖
> 緩衝位置與下面的背光行為,全部來自那台機器的實測。**5(800×480)** 與 5B 是同一片 PCB、
> 同一組腳位(微雪用 `waveshare_lcd_port.h` 裡一個巨集切換兩者),porch 與 pixel clock 直接
> 照抄官方範例,但只做過 config 與編譯驗證 —— 手上沒有 800×480 面板。
> **P4-7B 已實機燒錄**,面板、顏色、觸控都驗證過。有三件事必須同時正確,而且互相牽動:
> `byte_order` 要與 `lvgl` 區塊一致(這裡兩邊都是 `little_endian`,即 display 的預設值;
> 若讓 LVGL 留在它自己的 `big_endian` 預設,每個 RGB565 的位元組對會被交換,整片畫面偏
> 暗紅)、面板掃描方向與 UI 差 180 度所以要 `rotation: 180°` —— 本分支這一項寫在
> **`lvgl:`** 區塊而不是 `display:`,後者在 LVGL 9 會直接被拒絕(這個 model 標了
> `no_transform`,只能由 LVGL 軟體旋轉並另配一份旋轉緩衝)。
>
> 這個旋轉有兩個容易漏掉的連鎖效應,而且方向相反。LVGL 元件會把**指標輸入**也轉同樣
> 的角度,而 ESPHome 的觸控基底類別根本不看旋轉 —— 所以原點本來就對齊 UI 的 GT911
> 反而需要 `mirror_x` + `mirror_y` 去抵消 LVGL 那一次。但三指手勢讀的是觸控元件自己
> 的座標,**不經過** LVGL,拿到的是鏡像後的值,判斷式必須跟著反過來。改一邊就要改另一邊。
>
> **本分支的 microSD 可用。** 卡走原生 SDMMC —— CLK 43 / CMD 44 / D0-D3 39,40,41,42,
> slot 0,與 C6 佔用的 slot 1 不衝突。兩件不明顯的事:P4 的卡片 IO 電軌由晶片內部 LDO
> 供電,而預設沒有人會打開它(已修補進 vendored 的 `sd_storage`,通道 4,與 Espressif
> 官方 P4 BSP 一致);以及卡片必須是 **FAT32** —— exFAT 與 NTFS 都沒有編進去,而 NTFS
> 的失敗方式極具誤導性:它會成功讀到第 0 磁區,然後 FATFS 把 NTFS 的開機碼當成分割表,
> 去讀超出卡片容量的位置。
>
> **截圖也可用**,以 `esp_lcd_dpi_panel_get_frame_buffer()` 讀回 DPI framebuffer。
> 隨附兩個板檔旗標:`SHOT_SWAP_BYTES=0`(這裡的 framebuffer 是原生 RGB565,不是位元組
> 交換過的)、`RADAR_SHOT_ROT180=1`(LVGL 是先把 UI 轉好才送進 framebuffer,所以你看到
> 正立的畫面在裡面是顛倒的)。透過 C6 的 Wi-Fi 已確認可用。
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
