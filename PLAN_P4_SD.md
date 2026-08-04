# P4 microSD:截圖存到 TF 卡

目標:讓 Waveshare ESP32-P4-WIFI6-Touch-LCD-7B 的三指截圖除了 `:8081/screenshot.bmp`
之外,另存一份到 microSD —— 和 S3-5B 現有的行為一致。

## 為什麼只做在 `lvgl9` 分支

採用 p1ngb4ck fork 的 `sd_storage` 元件(方案 A)。它 import 了

```python
from esphome.components.esp32.const import VARIANT_ESP32P4, VARIANT_ESP32S3, VARIANT_ESP32S31
```

而 `VARIANT_ESP32S31` 只存在於較新的 ESPHome:

| 環境 | ESPHome | `VARIANT_ESP32S31` |
|---|---|---|
| `esphome`(`main`) | 2026.3.3 | 不存在 → ImportError |
| `esphome-lvgl9` | 2026.6.5 | 存在 |

所以 **P4 + SD 只能在 `lvgl9` 上建置**。`main` 的 P4 板檔維持現狀(無 SD)。

## 兩個各自獨立的半邊

這件事其實是兩個不相干的問題,任一邊壞掉另一邊仍可單獨驗證:

1. **把卡掛起來**(`/sdcard`)——靠 vendored `sd_storage`。
2. **讓 P4 有截圖可存**——目前 `-DRADAR_DISPLAY_RGB=0`,`screenshot_capture()` 是回傳
   false 的空實作,因為它呼叫的是並列 RGB 專用的 `esp_lcd_rgb_panel_get_frame_buffer()`。

## 已查證的事實

- `esphome::mipi_dsi::MipiDsi` 有 `protected: esp_lcd_panel_handle_t handle_{}`
  (`mipi_dsi.h:104`),形狀和 RGB 那兩個類別一樣 → 現有的 `RpiSpy` 取 handle 手法可原樣沿用。
- 面板由 `esp_lcd_new_panel_dpi()` 建立、`num_fbs = 1`(`mipi_dsi.cpp:76,94`),像素經
  `esp_lcd_panel_draw_bitmap()` 寫入 → 有一份完整的 DPI framebuffer,可用
  `esp_lcd_dpi_panel_get_frame_buffer()` 讀回。
- `rotation: 180°` 是 LVGL 的軟體旋轉,framebuffer 裡已經是轉正後的畫面 → 截圖不必再轉。
- 觸發點 `common/core.yaml:521` 的 `screenshot_capture(id(main_display))` 與板子無關,不用改。
- `sd_save_shot()` 掛載後只用標準 POSIX(`fopen("/sdcard/...")`,`radar_fetch.h:1028`)
  → 由誰掛載都行,只要跳過我們自己的 `sd_mount()`。
- fork 的 `sd_storage` 明確支援 P4(`SDMMC_VARIANTS = [S3, P4, S31]`),P4 走
  `SDMMC_FREQ_HIGHSPEED`(40MHz)。
- **但它完全沒有 P4 的 SD 供電處理**:`sd_storage.{cpp,h}`、`sd_storage_base.cpp`、
  `__init__.py` 四個檔案 grep `ldo|pwr_ctrl|power` 全部 0 命中,`host.pwr_ctrl_handle`
  從未設定。P4 的 SD IO 電軌由晶片內部 LDO 供電,不開就沒電。這是必須自己補的。
- Espressif 官方 P4 BSP 的做法(`esp-bsp/bsp/esp32_p4_function_ev_board/
  esp32_p4_function_ev_board.c:199`):
  ```c
  sd_pwr_ctrl_ldo_config_t ldo_config = { .ldo_chan_id = 4 };
  sd_pwr_ctrl_new_on_chip_ldo(&ldo_config, &pwr_ctrl_handle);
  cfg->host->pwr_ctrl_handle = pwr_ctrl_handle;
  ```
  該 BSP 的 SD 腳位 D0–D3 = 39,40,41,42 / CMD = 44 / CLK = 43,**與我們 P4 板檔第 65 行
  已記錄的 Waveshare 04_sdmmc 腳位完全相同** → 7B 沿用 EV Board 接線,LDO 通道極可能也是 4。
  (這一項是推論,要靠實機開機 log 確認。)
- `esp32_hosted` 用 SDMMC `slot: 1` 接 C6,`sd_storage` 預設 `slot: 0` → 不衝突。
- `storage` 元件是自足的(`DEPENDENCIES = []`、`AUTO_LOAD = []`),`sd_storage` 依賴
  `esp32` + `spi` + `storage`。兩者合計 16 個檔案約 121 KB,適合 vendor。

## 步驟

### 1. Vendor 元件
把 p1ngb4ck/esphome@`60c4707ecb52036759cc40c5a0ab3e4419dcc271`(dev,2026-07-06)的
`esphome/components/storage/` 與 `esphome/components/sd_storage/` 複製到 `components/`。
釘 commit,不用 `@dev` + `refresh: 0s`(移動中的分支,每次 build 可能拿到不同程式碼)。
沿用 `components/psram`、`components/lvgl` 既有的「本地覆寫」註解慣例,標明來源與修改處。

### 2. 補 P4 LDO
在 `sd_storage.cpp` 的 `SdMmc::mount()` 裡、`esp_vfs_fat_sdmmc_mount()` 之前加上
on-chip LDO 電源控制,並以 `#if defined(USE_ESP32_VARIANT_ESP32P4)` 包住。
LDO 通道做成可設定(預設 4),以免別的 P4 板子不同。

### 3. P4 板檔
- 開 fatfs(照 S3-5B 的寫法:`disable_fatfs: false` + `include_builtin_idf_components: [fatfs]`)
- 加 `sd_storage:` 區塊(腳位如上,`slot: 0`,`mount_path: /sdcard`)
- build flags:`-DRADAR_DISPLAY_RGB=3`(新值 = MIPI-DSI)、`-DRADAR_SD_EXT=1`

### 4. `radar_fetch.h`
- `RADAR_DISPLAY_RGB` 新增值 **3 = MIPI-DSI**:`MipiDsi` 版的 spy 類別 +
  `esp_lcd_dpi_panel_get_frame_buffer()`。其餘(`g_shot_buf`、BMP 標頭、列轉換、
  :8081 HTTP 服務、`sd_save_shot()`)全部共用。
  (巨集名字叫 RGB 但值 3 是 DSI,屬命名瑕疵;改名要動四個板檔加文件,不划算,註解說明即可。)
- 新增 `RADAR_SD_EXT`:`/sdcard` 由 ESPHome 元件掛載,我們的 `sd_mount()` 變成 no-op。
  把 `sd_save_shot()` 的檔案寫入部分從 `#if RADAR_SD_SPI` 改為兩種模式共用。

### 5. 建置與驗證
`conda activate esphome-lvgl9` + `ESPHOME_BUILD_PATH=build9 esphome compile radar-p4-7b.yaml`。
上機後看開機 log 的 `sd_storage` 掛載訊息確認 LDO 通道猜對了。

### 6. 收尾
README / docs/BOARDS.md(中英兩節)記錄 P4 的 SD 支援與版本限制;致謝加上 p1ngb4ck。
LDO 缺漏值得回報給 fork 作者——影響所有 P4 使用者。

## 風險

- LDO 通道 4 是推論。若開機 log 顯示掛載失敗,要查 7B 的實際原理圖。
- `esp_lcd_dpi_panel_enable_dma2d()` 有開,`draw_bitmap` 可能非同步;截圖讀 framebuffer
  時可能讀到半張。RGB 板也有同樣風險,現行做法可接受。
- vendor 進來的元件會跟著我們的 ESPHome 版本走,日後升級要重新對照上游。
