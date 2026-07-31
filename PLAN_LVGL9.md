# LVGL 8.4 → 9.5 移植(branch `lvgl9`)

目的:做出一份與 `main` 功能相同、但底層跑 LVGL 9.5 的韌體,讓同一片板子可以
A/B 比較速度(渲染延遲、lvgl 慢操作警告次數、觸控回應)。

## 版本對照

| | `main` | `lvgl9` |
|---|---|---|
| ESPHome | 2026.3.3(conda env `esphome`) | 2026.6.5(conda env `esphome-lvgl9`) |
| LVGL | 8.4.0 | 9.5.0 |
| 建置目錄 | `.esphome/build/` | `.esphome/build9/`(`ESPHOME_BUILD_PATH`) |

LVGL 9 不是自己換 PlatformIO 版本號就好:ESPHome 的 lvgl 元件本身是 LVGL 8 API 寫的。
上游 ESPHome **2026.4.0 已經整包升級到 LVGL 9.5**,所以這個分支的做法是
「升級 ESPHome + 把專案自己的 C++/YAML 跟著 LVGL 9 改」,不是自己改元件。

## 建置指令

```bash
conda activate esphome-lvgl9
ESPHOME_BUILD_PATH=.esphome/build9 esphome run radar-s3-5b.yaml
```

(`main` 分支照舊:`conda activate esphome`,不帶 `ESPHOME_BUILD_PATH`。
兩者建置目錄分開,切分支不會互相清掉編譯快取。)

## 改動清單

### 1. components/(本地覆寫元件)
- **刪掉 `components/lvgl/`**:那份覆寫的唯一目的是把繪圖緩衝改配內部 SRAM,
  ESPHome 2026.4+ 的 LVGL 9 元件已內建(`lv_alloc_draw_buf(size, internal=true)`,
  失敗才退回 PSRAM)。
- **`components/psram/__init__.py` 重新以 2026.6.5 為底**,再註解掉
  `CONFIG_SPIRAM_TIMING_TUNING_POINT_VIA_TEMPERATURE_SENSOR`(上游 2026.6.5 仍會
  無條件開啟,本板 flash 不在 IDF 支援名單 → 0x106 無限重開機)。
- 兩片 Waveshare S3 板檔的 `external_components` 由 `[psram, lvgl]` 改成 `[psram]`。

### 2. 繪圖緩衝大小
上游把 `buffer_size` 量化成 1/2/4/8,**19% 以下一律 frac=8**,無法再像 LVGL 8 分支
那樣壓到 1/16。1024x600 的 1/8 = 154KB 內部 SRAM;LVGL 8 分支實測這個大小會餓死
mbedtls(握手 -0x7F00)。若在 9.5 重現,解法是再開一份最小的 lvgl 覆寫把緩衝減半。
→ **測試時請看開機 log 有沒有 mbedtls/alloc 失敗、資料抓不抓得到。**

### 3. YAML
- P4 板檔的 `display: rotation: 180°` 要移到 `lvgl:` 區塊(LVGL 9 由 LVGL 自己轉),
  觸控的 `transform:` 同時移除(LVGL 會自動跟著轉)。
- S3 兩片板子沒有 rotation,不受影響。

### 4. C++(LVGL 9 API 改名/改結構)
好消息:LVGL 9 的 `lvgl.h` 無條件 include `src/lv_api_map_v8.h`,單純改名的東西
(`lv_obj_clear_flag/clear_state`、`lv_img_set_angle`、`lv_obj_set_style_img_recolor*`、
`lv_coord_t`、`lv_scr_act` …)都有相容別名,**不必動**。真正要改的是結構/語意變了的:

| LVGL 8 | LVGL 9 | 位置 |
|---|---|---|
| `lv_canvas_get_img()->data` | `lv_canvas_get_draw_buf()->data` | `radar_fetch.h` |
| 畫布像素 = `lv_color_t`(2 bytes)、`.full` | `lv_color_t` 變 24-bit,畫布是 RGB565 → 一律用 `uint16_t` + `lv_color_to_u16()` | `radar_fetch.h` |
| `lv_color_fill()` | 已移除 → 自己寫 16-bit 填充迴圈 | `radar_fetch.h` |
| `lv_color_mix()` | 混 RGB565 改用 `lv_color_16_16_mix()`(同樣是 FAST_MEM) | 回波預混合 |
| `lv_canvas_draw_line/arc/rect/text` | 全砍。改走 layer:`lv_canvas_init_layer` → `lv_draw_line/arc/rect/label` → `lv_canvas_finish_layer` | `radar_rebuild_base` |
| dsc 的座標由參數傳入 | 座標寫進 dsc(`p1/p2`、`center/radius`;label/rect 額外帶 `lv_area_t`) | 同上 |
| `lv_font_default()` | `lv_font_get_default()` | ATC 標籤 |
| `lv_line_set_points(o, lv_point_t*, n)` | 點陣列型別改成 `lv_point_precise_t` | `common/core.yaml` |
| `lv_textarea_del_char()` | `lv_textarea_delete_char()` | `ui/ui_*.yaml`(兩份都要改) |

繪圖任務是**排到 `finish_layer` 才執行**的,所以:
- dsc 裡不能指向區域變數(`points` 陣列、堆疊上的字串),本檔一律只用 `p1/p2` 與靜態字串;
- 上千段線一次排隊會吃掉大量 LVGL 堆積,故加了 `radar_bg::CanvasPainter`,每 128 個
  任務收一次 layer 再開新的。

### 5. 順帶被 ESPHome 版本影響的地方
- P4 板檔的 `i2s_audio: use_legacy: false`:2026.4+ 移除了 legacy I2S 驅動,連選項一起
  拿掉,留著會驗證失敗 → 已刪除該行。

## 驗證
1. ✅ `esphome config`:四份進入設定(`radar.yaml`、`radar-s3-5.yaml`、`radar-s3-5b.yaml`、
   `radar-p4-7b.yaml`)全部通過。
2. ✅ `esphome compile`:
   - `radar-s3-5b.yaml`(S3 1024x600):通過,RAM 21.5% / 70,552 B、Flash 2,334,155 B。
   - `radar-p4-7b.yaml`(P4 1024x600):通過,RAM 10.5% / 53,792 B、Flash 2,423,092 B。
     (第一次編譯在 IDF 的 `esp_driver_ana_cmpr/ana_cmpr_etm.c` 撞到 GCC internal
      compiler error: Segmentation fault,與本專案程式無關;重跑一次即過。)
3. ⬜ 上機(未做,需要實體板):看開機 log(繪圖緩衝落在內部 SRAM 還是 PSRAM、mbedtls
   有無 alloc 失敗)、底圖/回波/ATC 圖層外觀與 `main` 一致、觸控與換頁流暢度、
   `lvgl` 慢操作警告次數。P4 的觸控方向也只有上機才驗得了(見上)。

## 比較速度時建議看的數字
- 開機 log 的 `lvgl` 慢操作警告(`Component lvgl took …`)出現次數與毫秒數;
- 切換頁面、拖滑桿的手感;
- 重建底圖(改座標/範圍、開關 MAP/ATC)到畫面更新的延遲;
- 雷達掃描線的動畫是否平順。
