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

### 2. 繪圖緩衝大小 → 改用「TLS 記憶體搬去 PSRAM」解決
上游把 `buffer_size` 量化成 1/2/4/8,**19% 以下一律 frac=8**,無法再像 LVGL 8 分支
那樣壓到 1/16。1024x600 的 1/8 = 154KB 內部 SRAM。

實機上果然重現了 LVGL 8 分支那個老問題:

```
E (8280) Dynamic Impl: alloc(4770 bytes) failed
E (8280) esp-tls-mbedtls: mbedtls_ssl_handshake returned -0x7F00
W (8282) radar_bg: weather failed: -1
```

原因:mbedtls dynamic buffer 走 `esp_mbedtls_mem_calloc()`,預設是 `calloc()`,而
4770 < `CONFIG_SPIRAM_MALLOC_ALWAYSINTERNAL`(16KB)必定被導回內部 RAM;繪圖緩衝
把內部 RAM 吃掉後就配不出來。

**試過但失敗的解法**:板檔設 `CONFIG_MBEDTLS_EXTERNAL_MEM_ALLOC`,讓 TLS 自己的記憶體
改配 PSRAM(IDF 預設是 `CONFIG_MBEDTLS_INTERNAL_MEM_ALLOC=y`)。握手是過了,但問題只是
往下推一層:

```
E (44630) esp-aes: Failed to allocate memory
E (44630) esp-tls-mbedtls: read error :-0x0001
```

AES 硬體加速器走 DMA,來源在 PSRAM 時要另外配一塊「內部 DMA 跳板緩衝」
(`esp_aes_dma_core.c` 的 `realloc_input/realloc_output`,大小同 TLS record,可達 8KB),
內部 RAM 一樣配不出來。→ 已撤回。

**最後採用**:照 LVGL 8 分支的結論,把 `components/lvgl` 覆寫加回來,唯一改動是在
`LvglComponent::setup()` 內把緩衝再減半(1/8 → **1/16 = 77KB**)並明確要求
`MALLOC_CAP_INTERNAL`。這樣記憶體配置與 `main` 完全一致(mbedtls 照舊走內部 RAM),
**LVGL 版本成為唯一變數**,比較速度才公平。三種大小的實測取捨(LVGL 8 分支):
154KB 渲染最快但餓死 TLS;77KB 兩者兼得;38KB 因 flush 次數暴增反而更慢。

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

## 加速:平行繪圖單元(LVGL 9 專屬)

LVGL 9 把繪製拆成 draw unit + draw task 佇列;開了 OS 之後,每個軟體繪圖單元會有
自己的 FreeRTOS 執行緒(`lv_draw_sw.c` 的 `lv_draw_sw_init`),任務就能被兩條執行緒
同時消化。S3/P4 都是雙核,第二顆核心原本閒著。LVGL 8 沒有這個機制。

設定寫在 `common/core.yaml` 的 `platformio_options.build_flags`(ESPHome 沒把這些選項
開出來,但它產生 `lv_conf.h` 時會跳過任何已出現在 build_flags 裡的 `LV_*` 定義,
所以設得進去):

```yaml
- "-DLV_USE_OS=2"                     # LV_OS_FREERTOS
- "-DLV_DRAW_SW_DRAW_UNIT_CNT=2"
- "-DLV_USE_FREERTOS_TASK_NOTIFY=1"
- "-DLV_DRAW_THREAD_STACK_SIZE=32768"  # 見下,實際是 8KB/條
```

**踩到的坑**:LVGL 的 `lv_freertos.c` 把 `usStackSize / sizeof(StackType_t)` 丟給
`xTaskCreate`(vanilla FreeRTOS 的堆疊深度以「字」計),但 **ESP-IDF 的 xTaskCreate 收
的是「位元組」**。照 LVGL 預設 8KB 會變成實際 2KB → 繪圖執行緒爆堆疊。所以這裡填
32768(/4 = 實際 8KB),兩條執行緒共 16KB 內部 RAM。

執行緒安全:本專案所有 LVGL API 都在主迴圈任務裡呼叫(背景的 `radar_fetch` 任務只碰
自己的緩衝與旗標),所以不需要 `lv_lock()`。

**A/B 方法**:把那四行註解掉重編,就是單執行緒(與 LVGL 8 相同的行為)。開機 log 的
`dump_config` 會印 `SW draw units: 2 (threaded)` 或 `1 (single-threaded)`,可以確認生效。

### 實測結論:更慢,已預設關閉

5B 實機開了之後:

```
W lvgl took a long time for an operation (631 ms), max is 560 ms
W lvgl took a long time for an operation (708 ms), max is 660 ms
E Dynamic Impl: alloc(16937 bytes) failed        ← 兩條執行緒的 16KB 堆疊又把 TLS 擠爆
```

掃描線的延遲感也變重。推測原因:本專案的畫面是「很多小任務」(標籤、線段),
每個任務都要付一次執行緒同步的成本,而任務本身的工作量很小——管理成本吃掉了
平行化的好處。平行繪圖單元適合大面積、少量任務的畫面(例如整片漸層、大圖縮放)。

程式碼與註解都留著(`common/core.yaml` 裡註解掉的 build_flags),要再試很容易。

## 加速:底圖線條直接寫像素(取代 LVGL 的繪圖任務)

上面那筆 631~708ms 指向真正的瓶頸:**底圖重建**。LVGL 9 的每一筆 `lv_draw_*` 都要
配一個 draw task、複製一份 dsc、排隊,再等 `finish_layer` 派送執行(LVGL 8 的
`lv_canvas_draw_line` 是當場畫完)。底圖的地圖輪廓上千段、ATC 空域再上百段,全是
1px 純色線——不需要抗鋸齒也不需要混色,管理成本遠大於畫線本身。

`radar_bg::PixCanvas`(radar_fetch.h)直接對 canvas 的 RGB565 緩衝寫像素:
Cohen–Sutherland 裁切 + Bresenham,外加 `line2`(2px)與 `fill_rect`。改用它的有:

| 圖層 | 之前 | 現在 |
|---|---|---|
| 地圖輪廓(上千段) | `lv_draw_line` x N | `pc.line()` |
| 十字線 | `lv_draw_line` x2 | `pc.line()` |
| ATC 空域邊界 | `lv_draw_line` x N | `pc.line()` |
| 跑道 + 延伸虛線 | `lv_draw_line` x N | `pc.line()` / `pc.line2()` |
| 導航點三角 | `lv_draw_line` x3N | `pc.line()` |
| 機場方塊 | `lv_draw_rect` | `pc.fill_rect()` |
| **距離環(4 圈)** | `lv_draw_arc` | **不變**——圓弧抗鋸齒自己補不划算,且只有 4 個任務 |
| **所有文字標籤** | `lv_draw_label` | **不變**——字形點陣與字型度量交給 LVGL |

疊圖順序有保住:距離環的 `CanvasPainter` 用一個 scope 包起來,離開時 `finish_layer`
會把環真的畫進緩衝,之後 ATC 圖層的直接寫入才會蓋在環之上。導航點/機場則是
「圖形先全部寫完 → 再開一個 layer 一次畫所有標籤」,文字仍在最上層。

## 比較速度時建議看的數字
- 開機 log 的 `lvgl` 慢操作警告(`Component lvgl took …`)出現次數與毫秒數;
- 切換頁面、拖滑桿的手感;
- 重建底圖(改座標/範圍、開關 MAP/ATC)到畫面更新的延遲;
- 雷達掃描線的動畫是否平順。
