// 背景航班抓取引擎:跑在 core 1 的 FreeRTOS task,主迴圈(UI)完全不阻塞。
// 主迴圈用 request_states()/request_route() 丟工作,
// 每秒輪詢 g_states_ready / g_route_ready 取結果。
#pragma once
// ---- Per-board geometry (override via build_flags in boards/*.yaml) ----
//   RADAR_CANVAS  square radar canvas side (px); must equal the LVGL
//                 base_canvas size in the matching ui/ package.
//   SCREEN_W/H    panel size, used by the screenshot framebuffer copy.
//   RADAR_DISPLAY_RGB  which display driver the screenshot grab should use:
//                 1 = parallel-RGB via `rpi_dpi_rgb`  (generic 800x480 board)
//                 2 = parallel-RGB via `mipi_rgb`     (Waveshare Touch-LCD-5/5B)
//                 0 = neither (e.g. MIPI-DSI on ESP32-P4) -> screenshot disabled
//                 1 and 2 are both parallel-RGB panels, so the IDF call
//                 esp_lcd_rgb_panel_get_frame_buffer() works for both; only the
//                 ESPHome wrapper class holding the panel handle differs.
#ifndef RADAR_CANVAS
#define RADAR_CANVAS 456
#endif
#ifndef SCREEN_W
#define SCREEN_W 800
#endif
#ifndef SCREEN_H
#define SCREEN_H 480
#endif
#ifndef RADAR_DISPLAY_RGB
#define RADAR_DISPLAY_RGB 1
#endif
// 背光是否接在可 PWM 的原生 GPIO。Waveshare ESP32-S3-Touch-LCD-5/5B 的背光走
// CH422G 擴充腳(EXIO2),官方 waveshare_lcd_port.h 的 EXAMPLE_LCD_BL_IO = -1,
// 且 CH422G 無 PWM 通道 → 只能開/關。那些板子設 0,亮度滑桿改控 LVGL 暗化遮罩。
#ifndef RADAR_BL_PWM
#define RADAR_BL_PWM 1
#endif
// 三指截圖是否另存一份到 microSD。Waveshare Touch-LCD-5/5B 的 TF 走 SPI:
// MOSI/CLK/MISO 是原生 GPIO,但 CS 在 CH422G EXIO4(擴充腳,無法給 sdspi 驅動用)。
// 因為那條 SPI 上只有 SD 一個裝置,板檔用一個 gpio switch 於開機時把 EXIO4 拉低
// (restore_mode: ALWAYS_OFF)並保持,驅動這邊就以 SDSPI_SLOT_NO_CS 掛載。
// 沒有卡或掛載失敗時只是不寫檔,HTTP(:8081)那條路照舊。
#ifndef RADAR_SD_SPI
#define RADAR_SD_SPI 0
#endif
// 雷達可同時顯示的航班數(= ui/*.yaml 裡 ac/ai/sq/ad/vec/tr 這幾組 widget 的組數)。
// 資料端不設上限:radar_fetch 依距離由近而遠排序,超過這個數的遠機不繪出。
// 改這個值必須同步 ui/ui_800x480.yaml 的 widget 組數(並重跑 tools/scale_layout.py)。
#define AC_SLOTS 40
#define RADAR_CX (RADAR_CANVAS / 2)        // canvas center
#define RADAR_R  (RADAR_CANVAS / 2 - 2)    // usable radar radius
// UI scale factor vs the reference 800x480 layout (456px canvas). The LVGL
// layouts for other resolutions are generated from that reference by
// tools/scale_layout.py with the same round-half-up rule, so RS() of a
// reference-layout pixel value always lands on the generated widget position.
// Used by the YAML lambdas in common/core.yaml for page-coordinate math.
#define RADAR_SCALE ((float) RADAR_CANVAS / 456.0f)
#define RS(v) ((int) ((v) * RADAR_SCALE + 0.5f))
#include <string>
#include <vector>
#include <algorithm>
#include <cstring>
#include <cmath>
#include <map>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "freertos/queue.h"
#include "esp_http_client.h"
#include "esp_http_server.h"
#if RADAR_DISPLAY_RGB
#include "esp_lcd_panel_rgb.h"
#endif
#include "esp_heap_caps.h"
#include "esp_flash.h"
#include "esp_ota_ops.h"
#include "esp_rom_sys.h"
#include "esp_timer.h"
#if RADAR_SD_SPI
#include "driver/spi_common.h"
#include "driver/sdspi_host.h"
#include "sdmmc_cmd.h"
#include "esp_vfs_fat.h"
#include <ctime>
#endif
extern "C" {
#include "pngle.h"
}
#include "esp_log.h"
#include "esphome/components/json/json_util.h"
#include "esphome/components/image/image.h"
#if RADAR_DISPLAY_RGB == 1
#include "esphome/components/rpi_dpi_rgb/rpi_dpi_rgb.h"
#elif RADAR_DISPLAY_RGB == 2
#include "esphome/components/mipi_rgb/mipi_rgb.h"
#endif
#include "map_data.h"

namespace radar_bg {

struct AcInfo {
  float lat, lon, trk, vel, alt, vr, dist;
  uint32_t lc;   // last_contact (epoch 秒),ATC 模式判斷訊號延遲用
  std::string cs;
  std::string sq;   // squawk / mode-A code(三家來源都有;OpenSky 是 states[14])
  std::string ty;   // ICAO 機型代碼(如 B738);只有 airplanes.live / adsb.lol 提供
};

struct Job {
  int type;  // 1 = states, 2 = route, 3 = echo, 4 = weather, 5 = speakers, 6 = route cache
  std::string cid, sec, callsign;
  float lat, lon, range;
  int src;   // states 資料來源:0=OpenSky 1=airplanes.live 2=adsb.lol
};

// ---- task → main 的結果(g_states_ready/g_route_ready 當柵欄)----
inline std::vector<AcInfo> g_result;
inline volatile bool g_states_ready = false;
inline std::string g_route;
inline volatile bool g_route_ready = false;
inline uint8_t *g_echo_buf = nullptr;    // 離屏合成緩衝 456*456*3 (PSRAM)
inline volatile bool g_echo_ready = false;   // true=g_echo_buf 有整幀待主迴圈換上
// 回波非透明像素的逐列水平範圍(x0 > x1 表示該列全透明)。
// 底圖重建每次都要把回波混進去,原本是整張 RADAR_CANVAS² 逐像素掃(570² =
// 324,900 次,每次讀 3 bytes PSRAM ≈ 950KB),但降雨通常只佔畫面一小塊、常常
// 甚至整張全空。合成時順手記下每列的左右界,混合就只走真的有資料的區段;
// 空白列連一次 PSRAM 讀取都不必。初值 0/0 是安全的:未寫入的緩衝 alpha=0,
// 混合迴圈本來就會跳過。
inline int16_t g_echo_x0[RADAR_CANVAS];
inline int16_t g_echo_x1[RADAR_CANVAS];
inline void echo_spans_clear() {
  for (int y = 0; y < RADAR_CANVAS; y++) { g_echo_x0[y] = RADAR_CANVAS; g_echo_x1[y] = -1; }
}
inline volatile bool g_auth_fail = false;
struct WxInfo { float temp, hum, wspd, wdir; };   // 在地天氣(Open-Meteo)
inline WxInfo g_wx;
inline volatile bool g_wx_ready = false;   // true=g_wx 有新資料待主迴圈取用
inline bool g_wx_valid = false;            // 曾成功抓過至少一次
inline std::string g_speakers;             // HA 喇叭清單:每行 entity_id|friendly_name
inline volatile bool g_speakers_ready = false;
inline int g_spk_status = 0;               // HTTP 狀態:200 成功 / 401 token 錯 / <=0 連不上

inline volatile int g_os_remaining = -1;   // OpenSky X-Rate-Limit-Remaining(-1=未知)
inline bool g_want_rl = false;             // 只在 states 請求期間擷取(bg task 序列執行,無競態)
inline volatile uint32_t g_os_cooldown_until = 0;  // OpenSky 失敗冷卻期限(millis 秒),期間走免費來源
inline volatile int g_last_src = -1;       // 最近一次成功抓取的來源(0/1/2,-1=尚未成功)

inline esp_err_t http_evt_cb(esp_http_client_event_t *evt) {
  if (evt->event_id == HTTP_EVENT_ON_HEADER && g_want_rl &&
      strcasecmp(evt->header_key, "X-Rate-Limit-Remaining") == 0)
    g_os_remaining = atoi(evt->header_value);
  return ESP_OK;
}

inline SemaphoreHandle_t mtx() {
  static SemaphoreHandle_t m = xSemaphoreCreateMutex();
  return m;
}
inline QueueHandle_t queue() {
  static QueueHandle_t q = xQueueCreate(4, sizeof(Job *));
  return q;
}

// ---- 簡易 HTTP(直接用 esp_http_client,不經 ESPHome 元件)----
inline std::string http_req(const std::string &url, bool post, const std::string &body,
                            const char *ctype, const std::string &bearer, int &status,
                            size_t reserve_hint = 8192) {
  esp_http_client_config_t cfg = {};
  cfg.url = url.c_str();
  cfg.timeout_ms = 20000;
  cfg.buffer_size = 4096;
  cfg.buffer_size_tx = 8192;   // OpenSky JWT 很大
  cfg.method = post ? HTTP_METHOD_POST : HTTP_METHOD_GET;
  cfg.event_handler = http_evt_cb;   // 擷取 OpenSky 額度 header(g_want_rl 才動作)
  status = -1;
  esp_http_client_handle_t c = esp_http_client_init(&cfg);
  if (c == nullptr) return "";
  if (ctype != nullptr) esp_http_client_set_header(c, "Content-Type", ctype);
  std::string auth;
  if (!bearer.empty()) {
    auth = "Bearer " + bearer;
    esp_http_client_set_header(c, "Authorization", auth.c_str());
  }
  std::string out;
  out.reserve(reserve_hint);   // >16KB 的配置會進 PSRAM(SPIRAM_USE_MALLOC)
  if (esp_http_client_open(c, body.size()) == ESP_OK) {
    if (!body.empty()) esp_http_client_write(c, body.c_str(), body.size());
    esp_http_client_fetch_headers(c);
    status = esp_http_client_get_status_code(c);
    char buf[2048];
    int n;
    while ((n = esp_http_client_read(c, buf, sizeof(buf))) > 0) {
      out.append(buf, n);
      if (out.size() > 150000) break;
    }
  }
  esp_http_client_close(c);
  esp_http_client_cleanup(c);
  return out;
}

// ---- OpenSky token(task 內部狀態)----
inline std::string t_token;
inline uint32_t t_token_exp = 0;

inline bool ensure_token(const Job &j) {
  if (!t_token.empty() && (millis() / 1000) < t_token_exp) return true;
  int st = 0;
  std::string b = "grant_type=client_credentials&client_id=" + j.cid +
                  "&client_secret=" + j.sec;
  std::string r = http_req(
      "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token",
      true, b, "application/x-www-form-urlencoded", "", st);
  if (st != 200 || r.empty()) {
    ESP_LOGW("radar_bg", "token failed: %d", st);
    t_token.clear();
    g_auth_fail = true;
    return false;
  }
  bool ok = esphome::json::parse_json(r, [](JsonObject root) -> bool {
    t_token = (const char *) (root["access_token"] | "");
    uint32_t exp = root["expires_in"] | 1800;
    t_token_exp = millis() / 1000 + exp - 120;
    return true;
  });
  if (!ok || t_token.empty()) { g_auth_fail = true; return false; }
  ESP_LOGI("radar_bg", "token OK");
  return true;
}

inline bool do_states_opensky(const Job &j) {
  if (!ensure_token(j)) return false;
  float coslat = cosf(j.lat * 3.14159265f / 180.0f);
  float dlat = j.range / 110.574f;
  float dlon = j.range / (111.320f * coslat);
  char url[192];
  snprintf(url, sizeof(url),
           "https://opensky-network.org/api/states/all?lamin=%.4f&lomin=%.4f&lamax=%.4f&lomax=%.4f",
           j.lat - dlat, j.lon - dlon, j.lat + dlat, j.lon + dlon);
  int st = 0;
  g_want_rl = true;
  std::string r = http_req(url, false, "", nullptr, t_token, st, 131072);
  g_want_rl = false;
  if (st == 401) { t_token.clear(); return false; }   // 下一輪重新換發
  if (st != 200 || r.empty()) {
    ESP_LOGW("radar_bg", "states failed: %d (%u bytes)", st, (unsigned) r.size());
    return false;
  }
  std::vector<AcInfo> acs;
  float lat0 = j.lat, lon0 = j.lon;
  esphome::json::parse_json(r, [&](JsonObject root) -> bool {
    JsonArray sts = root["states"].as<JsonArray>();
    if (sts.isNull()) return true;
    for (JsonVariant v : sts) {
      JsonArray a = v.as<JsonArray>();
      if (a.isNull()) continue;
      if (a[8] | false) continue;                 // on_ground
      float alon = a[5] | NAN, alat = a[6] | NAN;
      if (isnan(alon) || isnan(alat)) continue;
      AcInfo ac;
      ac.lat = alat; ac.lon = alon;
      ac.alt = a[7] | 0.0f;
      ac.vel = a[9] | 0.0f;
      ac.trk = a[10] | 0.0f;
      ac.vr  = a[11] | 0.0f;
      ac.lc  = a[4] | 0u;
      ac.sq  = a[14] | "";     // squawk;OpenSky 不提供機型,ty 留空
      const char *c = a[1] | "";
      ac.cs = c;
      while (!ac.cs.empty() && ac.cs.back() == ' ') ac.cs.pop_back();
      if (ac.cs.empty()) ac.cs = "?";
      float e = (alon - lon0) * 111.320f * coslat;
      float n = (alat - lat0) * 110.574f;
      ac.dist = sqrtf(e * e + n * n);
      acs.push_back(ac);
    }
    return true;
  });
  std::sort(acs.begin(), acs.end(),
            [](const AcInfo &a, const AcInfo &b) { return a.dist < b.dist; });
  xSemaphoreTake(mtx(), portMAX_DELAY);
  g_result = std::move(acs);
  g_states_ready = true;
  g_last_src = 0;
  xSemaphoreGive(mtx());
  return true;
}

// airplanes.live / adsb.lol(readsb /v2/point,免金鑰):回傳英制,這裡換算回公制
// 使 UI/ATC 端與 OpenSky 完全同構;lc 由 now(epoch ms)- seen 還原成 last_contact
inline bool do_states_v2(const Job &j, int src) {
  float r_nm = j.range / 1.852f;
  if (r_nm > 250.0f) r_nm = 250.0f;   // v2 API 半徑上限 250 nm(463 km)
  char url[160];
  snprintf(url, sizeof(url), "https://%s/v2/point/%.4f/%.4f/%.0f",
           src == 2 ? "api.adsb.lol" : "api.airplanes.live", j.lat, j.lon, r_nm);
  int st = 0;
  std::string r = http_req(url, false, "", nullptr, "", st, 131072);
  if (st != 200 || r.empty()) {
    ESP_LOGW("radar_bg", "v2 states(src %d) failed: %d (%u bytes)", src, st, (unsigned) r.size());
    return false;
  }
  std::vector<AcInfo> acs;
  float lat0 = j.lat, lon0 = j.lon;
  float coslat = cosf(j.lat * 3.14159265f / 180.0f);
  esphome::json::parse_json(r, [&](JsonObject root) -> bool {
    uint32_t now_s = (uint32_t) ((root["now"] | 0.0) / 1000.0);
    JsonArray arr = root["ac"].as<JsonArray>();
    if (arr.isNull()) return true;
    for (JsonVariant v : arr) {
      JsonObject a = v.as<JsonObject>();
      if (a.isNull()) continue;
      if (a["alt_baro"].is<const char *>()) continue;   // "ground" = 地面,跳過
      float alat = a["lat"] | NAN, alon = a["lon"] | NAN;
      if (isnan(alat) || isnan(alon)) continue;
      AcInfo ac;
      ac.lat = alat; ac.lon = alon;
      ac.alt = (a["alt_baro"] | 0.0f) * 0.3048f;    // ft → m
      ac.vel = (a["gs"] | 0.0f) * 0.514444f;        // kt → m/s
      ac.trk = a["track"] | 0.0f;
      ac.vr  = (a["baro_rate"] | 0.0f) * 0.00508f;  // ft/min → m/s
      float seen = a["seen"] | 0.0f;
      ac.lc = now_s > (uint32_t) seen ? now_s - (uint32_t) seen : 0;
      ac.sq = a["squawk"] | "";
      ac.ty = a["t"] | "";     // ICAO 機型代碼
      const char *c = a["flight"] | "";
      ac.cs = c;
      while (!ac.cs.empty() && ac.cs.back() == ' ') ac.cs.pop_back();
      if (ac.cs.empty()) ac.cs = "?";
      float e = (alon - lon0) * 111.320f * coslat;
      float n = (alat - lat0) * 110.574f;
      ac.dist = sqrtf(e * e + n * n);
      acs.push_back(ac);
    }
    return true;
  });
  std::sort(acs.begin(), acs.end(),
            [](const AcInfo &a, const AcInfo &b) { return a.dist < b.dist; });
  xSemaphoreTake(mtx(), portMAX_DELAY);
  g_result = std::move(acs);
  g_states_ready = true;
  g_last_src = src;
  xSemaphoreGive(mtx());
  return true;
}

inline void do_states(const Job &j) {
  if (j.src == 1 || j.src == 2) { do_states_v2(j, j.src); return; }
  // OpenSky 主線:冷卻中直接走免費來源;失敗設 10 分鐘冷卻,到期自動回試
  uint32_t now = millis() / 1000;
  if (now >= g_os_cooldown_until) {
    if (do_states_opensky(j)) { g_os_cooldown_until = 0; return; }
    g_os_cooldown_until = now + 600;
    ESP_LOGW("radar_bg", "opensky failed, fallback to free sources for 600s");
  }
  if (!do_states_v2(j, 1)) do_states_v2(j, 2);   // airplanes.live → adsb.lol
}

inline void do_route(const Job &j) {
  int st = 0;
  std::string r = http_req("https://api.adsbdb.com/v0/callsign/" + j.callsign,
                           false, "", nullptr, "", st);
  std::string rt = "ROUTE N/A";
  if (st == 200 && !r.empty()) {
    esphome::json::parse_json(r, [&](JsonObject root) -> bool {
      JsonObject fr = root["response"]["flightroute"];
      if (!fr.isNull()) {
        const char *o = fr["origin"]["iata_code"] | "";
        const char *d = fr["destination"]["iata_code"] | "";
        if (o[0] != 0 && d[0] != 0)
          rt = std::string("ROUTE  ") + o + " - " + d;
      }
      return true;
    });
  }
  xSemaphoreTake(mtx(), portMAX_DELAY);
  g_route = rt;
  g_route_ready = true;
  xSemaphoreGive(mtx());
}

// ---- 全機隊起訖站快取(ATC ROUTE 標籤行)----
// callsign → "KHH-KIX";"" = 查詢中,"-" = 查無資料(不再重查)。
// 與 g_route 同一把 mtx 保護;背景 task 逐架查 adsbdb,查過即快取。
inline std::map<std::string, std::string> g_rcache;

inline void do_route_cache(const Job &j) {
  int st = 0;
  std::string r = http_req("https://api.adsbdb.com/v0/callsign/" + j.callsign,
                           false, "", nullptr, "", st);
  std::string rt = "-";
  if (st == 200 && !r.empty()) {
    esphome::json::parse_json(r, [&](JsonObject root) -> bool {
      JsonObject fr = root["response"]["flightroute"];
      if (!fr.isNull()) {
        const char *o = fr["origin"]["iata_code"] | "";
        const char *d = fr["destination"]["iata_code"] | "";
        if (o[0] != 0 && d[0] != 0) rt = std::string(o) + "-" + d;
      }
      return true;
    });
  } else if (st != 200 && st != 404) {
    // 非 404 的失敗(網路/限流)不寫入快取,之後重試
    xSemaphoreTake(mtx(), portMAX_DELAY);
    g_rcache.erase(j.callsign);
    xSemaphoreGive(mtx());
    return;
  }
  xSemaphoreTake(mtx(), portMAX_DELAY);
  g_rcache[j.callsign] = rt;
  xSemaphoreGive(mtx());
}

// Open-Meteo 目前天氣(免金鑰、開源資料)→ g_wx
inline void do_weather(const Job &j) {
  char url[224];
  snprintf(url, sizeof(url),
           "https://api.open-meteo.com/v1/forecast?latitude=%.4f&longitude=%.4f"
           "&current=temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m",
           j.lat, j.lon);
  int st = 0;
  std::string r = http_req(url, false, "", nullptr, "", st);
  if (st != 200 || r.empty()) {
    ESP_LOGW("radar_bg", "weather failed: %d", st);
    return;
  }
  WxInfo w{};
  bool got = false;
  esphome::json::parse_json(r, [&](JsonObject root) -> bool {
    JsonObject cur = root["current"];
    if (cur.isNull()) return true;
    w.temp = cur["temperature_2m"] | NAN;
    w.hum  = cur["relative_humidity_2m"] | NAN;
    w.wspd = cur["wind_speed_10m"] | NAN;
    w.wdir = cur["wind_direction_10m"] | NAN;
    got = !isnan(w.temp);
    return true;
  });
  if (!got) { ESP_LOGW("radar_bg", "weather parse fail"); return; }
  xSemaphoreTake(mtx(), portMAX_DELAY);
  g_wx = w;
  g_wx_valid = true;
  g_wx_ready = true;
  xSemaphoreGive(mtx());
}

// 用 HA REST /api/template 列出所有 media_player(j.cid=HA URL、j.sec=長期 token)
inline void do_speakers(const Job &j) {
  std::string url = j.cid;
  while (!url.empty() && url.back() == '/') url.pop_back();
  url += "/api/template";
  // Jinja 模板在 HA 端渲染,回應為純文字:每行 entity_id|friendly_name
  std::string body =
      "{\"template\":\"{% for e in states.media_player %}"
      "{{ e.entity_id }}|{{ e.name }}\\n{% endfor %}\"}";
  int st = 0;
  std::string r = http_req(url, true, body, "application/json", j.sec, st);
  ESP_LOGI("radar_bg", "speakers http %d (%u bytes)", st, (unsigned) r.size());
  xSemaphoreTake(mtx(), portMAX_DELAY);
  g_spk_status = st;
  g_speakers = (st == 200) ? r : "";
  g_speakers_ready = true;
  xSemaphoreGive(mtx());
}

// ---- pngle 解碼 context:把 tile 像素寫進 512x512 RGBA 暫存 ----
struct PngCtx { uint8_t *rgba; int w, h; };

inline void png_on_draw(pngle_t *p, uint32_t x, uint32_t y, uint32_t w, uint32_t h,
                        const uint8_t rgba[4]) {
  PngCtx *c = (PngCtx *) pngle_get_user_data(p);
  for (uint32_t yy = y; yy < y + h && (int) yy < c->h; yy++) {
    for (uint32_t xx = x; xx < x + w && (int) xx < c->w; xx++) {
      uint8_t *d = c->rgba + ((size_t) yy * c->w + xx) * 4;
      d[0] = rgba[0]; d[1] = rgba[1]; d[2] = rgba[2]; d[3] = rgba[3];
    }
  }
}

// 下載單一 tile PNG → pngle 解碼進 tmp RGBA → 取樣合成進 g_echo_buf 的子矩形
// canvas 3 bytes/px:[color_lo][color_hi][alpha](= LVGL TRUE_COLOR_ALPHA 16bpp)
inline void echo_composite_tile(const std::string &url, uint8_t *tmp, int tw, int th,
                                int i, int j, float bx, float by,
                                float tile_km, float range) {
  int st = 0;
  std::string png = http_req(url, false, "", nullptr, "", st, 32768);
  if (st != 200 || png.empty()) { ESP_LOGW("radar_bg", "tile http %d", st); return; }
  memset(tmp, 0, (size_t) tw * th * 4);
  pngle_t *p = pngle_new();
  if (!p) return;
  PngCtx ctx = { tmp, tw, th };
  pngle_set_user_data(p, &ctx);
  pngle_set_draw_callback(p, png_on_draw);
  int fed = pngle_feed(p, png.data(), png.size());
  int iw = pngle_get_width(p);
  pngle_destroy(p);
  if (iw <= 0) iw = tw;
  if (fed < 0) { ESP_LOGW("radar_bg", "png decode err"); return; }

  float kmpp = 2.0f * range / (float) RADAR_CANVAS;
  float inv = tile_km / kmpp;
  int x_lo = (int) floorf(RADAR_CX + ((float) i - bx) * inv);
  int x_hi = (int) ceilf (RADAR_CX + ((float) (i + 1) - bx) * inv);
  int y_lo = (int) floorf(RADAR_CX + ((float) j - by) * inv);
  int y_hi = (int) ceilf (RADAR_CX + ((float) (j + 1) - by) * inv);
  if (x_lo < 0) x_lo = 0; if (x_hi > RADAR_CANVAS) x_hi = RADAR_CANVAS;
  if (y_lo < 0) y_lo = 0; if (y_hi > RADAR_CANVAS) y_hi = RADAR_CANVAS;
  for (int y = y_lo; y < y_hi; y++) {
    float ky = by * tile_km + (y - RADAR_CX) * kmpp;
    int tj = (int) floorf(ky / tile_km);
    if (tj != j) continue;
    int ty = (int) ((ky - j * tile_km) / tile_km * th);
    if (ty < 0 || ty >= th) continue;
    int dy2 = (y - RADAR_CX) * (y - RADAR_CX);
    uint8_t *orow = g_echo_buf + (size_t) y * RADAR_CANVAS * 3;
    for (int x = x_lo; x < x_hi; x++) {
      float kx = bx * tile_km + (x - RADAR_CX) * kmpp;
      int ti = (int) floorf(kx / tile_km);
      if (ti != i) continue;
      if ((x - RADAR_CX) * (x - RADAR_CX) + dy2 > RADAR_R * RADAR_R) continue;   // 圓外(留透明)
      int tx = (int) ((kx - i * tile_km) / tile_km * tw);
      if (tx < 0 || tx >= tw) continue;
      uint8_t *sp = tmp + ((size_t) ty * tw + tx) * 4;
      if (sp[3] < 32) continue;   // 無降雨=透明
      lv_color_t col = lv_color_make(sp[0], sp[1], sp[2]);
      uint8_t *op = orow + (size_t) x * 3;
      op[0] = col.full & 0xFF;
      op[1] = (col.full >> 8) & 0xFF;
      op[2] = sp[3];
      if (x < g_echo_x0[y]) g_echo_x0[y] = (int16_t) x;   // 這列有降雨的左右界,
      if (x > g_echo_x1[y]) g_echo_x1[y] = (int16_t) x;   // 供底圖混合跳過空白區
    }
  }
}

// RainViewer:抓最新圖層 → 2x2 拼磚,全程背景下載+解碼+合成到 g_echo_buf
inline void do_echo(const Job &j) {
  int st = 0;
  std::string r = http_req("https://api.rainviewer.com/public/weather-maps.json",
                           false, "", nullptr, "", st);
  if (st != 200 || r.empty()) { ESP_LOGW("radar_bg", "rainviewer meta %d", st); return; }
  std::string host, path;
  esphome::json::parse_json(r, [&](JsonObject root) -> bool {
    host = (const char *) (root["host"] | "");
    JsonArray past = root["radar"]["past"].as<JsonArray>();
    if (!past.isNull() && past.size() > 0)
      path = (const char *) (past[past.size() - 1]["path"] | "");
    return true;
  });
  if (host.empty() || path.empty()) return;
  float latr = j.lat * 3.14159265f / 180.0f;
  int zbest = -1; float tkm = 0;
  for (int z = 7; z >= 2; z--) {
    float tile_km = 40075.017f * cosf(latr) / (float) (1 << z);
    if (tile_km >= 2.0f * j.range) { zbest = z; tkm = tile_km; break; }
  }
  if (zbest < 0) { ESP_LOGW("radar_bg", "range too large"); return; }
  float n = (float) (1 << zbest);
  float xf = (j.lon + 180.0f) / 360.0f * n;
  float yf = (1.0f - asinhf(tanf(latr)) / 3.14159265f) / 2.0f * n;
  long x0 = (long) floorf(xf - 0.5f);
  long y0 = (long) floorf(yf - 0.5f);
  float bx = xf - x0, by = yf - y0;

  // 緩衝(PSRAM):離屏 456*456*3 + tile 暫存 512*512*4
  const int TW = 512, TH = 512;
  if (!g_echo_buf)
    g_echo_buf = (uint8_t *) heap_caps_malloc((size_t) RADAR_CANVAS * RADAR_CANVAS * 3, MALLOC_CAP_SPIRAM);
  static uint8_t *tmp = nullptr;
  if (!tmp) tmp = (uint8_t *) heap_caps_malloc((size_t) TW * TH * 4, MALLOC_CAP_SPIRAM);
  if (!g_echo_buf || !tmp) { ESP_LOGE("radar_bg", "echo buf alloc fail"); return; }

  memset(g_echo_buf, 0, (size_t) RADAR_CANVAS * RADAR_CANVAS * 3);   // 先清成透明(離屏,不影響畫面)
  echo_spans_clear();   // 逐列範圍跟著歸零,不然會留著上一幀的降雨區
  for (int k = 0; k < 4; k++) {
    char url[200];
    snprintf(url, sizeof(url), "%s%s/512/%d/%ld/%ld/2/1_1.png",
             host.c_str(), path.c_str(), zbest, x0 + k % 2, y0 + k / 2);
    echo_composite_tile(url, tmp, TW, TH, k % 2, k / 2, bx, by, tkm, j.range);
    vTaskDelay(pdMS_TO_TICKS(2500));   // 每塊間隔,分散 PSRAM/網路壓力
  }
  xSemaphoreTake(mtx(), portMAX_DELAY);
  g_echo_ready = true;   // 整幀就緒,等主迴圈 memcpy 換上
  xSemaphoreGive(mtx());
  ESP_LOGI("radar_bg", "echo frame ready z=%d tile=%.0fkm", zbest, tkm);
}

inline void task_fn(void *arg) {
  for (;;) {
    Job *j = nullptr;
    if (xQueueReceive(queue(), &j, portMAX_DELAY) == pdTRUE && j != nullptr) {
      if (j->type == 1) do_states(*j);
      else if (j->type == 2) do_route(*j);
      else if (j->type == 6) do_route_cache(*j);
      else if (j->type == 3) do_echo(*j);
      else if (j->type == 4) do_weather(*j);
      else if (j->type == 5) do_speakers(*j);
      delete j;
    }
  }
}

inline void ensure_task() {
  static bool created = false;
  if (!created) {
    created = true;
    xTaskCreatePinnedToCore(task_fn, "radar_fetch", 12288, nullptr, 1, nullptr, 1);
  }
}

inline void request_states(const std::string &cid, const std::string &sec,
                           float lat, float lon, float range, int src) {
  ensure_task();
  Job *j = new Job{1, cid, sec, "", lat, lon, range, src};
  if (xQueueSend(queue(), &j, 0) != pdTRUE) delete j;
}

inline void request_echo(float lat, float lon, float range) {
  ensure_task();
  Job *j = new Job{3, "", "", "", lat, lon, range};
  if (xQueueSend(queue(), &j, 0) != pdTRUE) delete j;
}

inline void request_weather(float lat, float lon) {
  ensure_task();
  Job *j = new Job{4, "", "", "", lat, lon, 0};
  if (xQueueSend(queue(), &j, 0) != pdTRUE) delete j;
}

inline void request_speakers(const std::string &url, const std::string &token) {
  ensure_task();
  Job *j = new Job{5, url, token, "", 0, 0, 0};
  if (xQueueSend(queue(), &j, 0) != pdTRUE) delete j;
}

inline void request_route(const std::string &cs) {
  if (cs.empty()) return;
  ensure_task();
  Job *j = new Job{2, "", "", cs, 0, 0, 0};
  if (xQueueSend(queue(), &j, 0) != pdTRUE) delete j;
}

// 查起訖站快取;未知就排一次背景查詢。回傳 "" = 還不知道,"-" = 查無資料。
// 佇列滿(深度 4)時清掉「查詢中」標記,下一幀重試,路線會分幾秒陸續補齊。
inline std::string route_cache_get(const std::string &cs) {
  if (cs.empty()) return "";
  ensure_task();
  xSemaphoreTake(mtx(), portMAX_DELAY);
  auto it = g_rcache.find(cs);
  if (it != g_rcache.end()) {
    std::string v = it->second;
    xSemaphoreGive(mtx());
    return v;
  }
  if (g_rcache.size() > 120) g_rcache.clear();   // 防跨日航班累積吃 PSRAM
  g_rcache[cs] = "";                             // 標記查詢中(去重)
  xSemaphoreGive(mtx());
  Job *j = new Job{6, "", "", cs, 0, 0, 0};
  if (xQueueSend(queue(), &j, 0) != pdTRUE) {
    delete j;
    xSemaphoreTake(mtx(), portMAX_DELAY);
    g_rcache.erase(cs);
    xSemaphoreGive(mtx());
  }
  return "";
}

// ---- 時區:下拉選單 index → POSIX TZ 字串(供 time.set_timezone 執行期切換)----
// 顯示名清單在 ui/ 的 dropdown options,兩邊 index 必須對齊。
inline const char *tz_posix(int i) {
  static const char *const T[] = {
      "CST-8",                            // 0 Taipei
      "JST-9",                            // 1 Tokyo
      "CST-8",                            // 2 Shanghai
      "HKT-8",                            // 3 Hong Kong
      "KST-9",                            // 4 Seoul
      "ICT-7",                            // 5 Bangkok
      "GMT0BST,M3.5.0/1,M10.5.0",         // 6 London
      "CET-1CEST,M3.5.0,M10.5.0/3",       // 7 Paris
      "CET-1CEST,M3.5.0,M10.5.0/3",       // 8 Berlin
      "EST5EDT,M3.2.0,M11.1.0",           // 9 New York
      "PST8PDT,M3.2.0,M11.1.0",           // 10 Los Angeles
      "UTC0",                             // 11 UTC
  };
  const int n = sizeof(T) / sizeof(T[0]);
  return (i >= 0 && i < n) ? T[i] : T[0];
}

}  // namespace radar_bg

// ---- 底圖層:底色+輪廓(快取)+ 預混合回波 + 距離環/十字線 → 單一不透明 canvas ----
// 貴的輪廓重畫(逐段 draw context,~40ms)只在座標/範圍/MAP 開關變更時做並存入快取;
// 平時重建 = memcpy 快取 + 回波混色 + 畫環,~15ms。距離環/十字線內容不變但位於
// map/echo 之上,烤進底圖後每幀連這幾個 widget 的圓弧邊框繪製也省掉。
// alpha 混色只在資料更新時做這一次,之後每幀渲染對這層只剩不透明 blit(省 PSRAM 頻寬)。
// ATC 圖層 bitmask:bit0 空域 / bit1 跑道 / bit2 機場 / bit3 導航點;ATC 模式關閉 = 0
inline uint8_t atc_layer_mask(bool atc, bool asp, bool rwy, bool apt, bool fix) {
  return atc ? (uint8_t) ((asp ? 1 : 0) | (rwy ? 2 : 0) | (apt ? 4 : 0) | (fix ? 8 : 0)) : 0;
}

inline void radar_rebuild_base(lv_obj_t *cv, float lat0, float lon0, float rng,
                               bool map_show, bool echo_show, uint8_t atc_layers) {
  lv_img_dsc_t *img = lv_canvas_get_img(cv);
  if (!img || !img->data) return;
  const size_t BYTES = (size_t) RADAR_CANVAS * RADAR_CANVAS * sizeof(lv_color_t);
  static uint8_t *cache = nullptr;   // 底色+輪廓快取(PSRAM,416KB)
  if (!cache) cache = (uint8_t *) heap_caps_malloc(BYTES, MALLOC_CAP_SPIRAM);
  static float c_lat = NAN, c_lon = NAN, c_rng = NAN;
  static bool c_map = false;
  bool fresh = cache && c_lat == lat0 && c_lon == lon0 && c_rng == rng && c_map == map_show;
  if (fresh) {
    memcpy((void *) img->data, cache, BYTES);
  } else {
    // 不要用 lv_canvas_fill_bg:它逐像素呼叫 set_px_color + set_px_alpha
    // (570x570 = 324,900 次 x2),每次都重算 offset 再走 lv_memcpy_small。
    // 1024x600 的 RGB 面板 GDMA 同時在吃 PSRAM 頻寬,兩者相撞會慢到每像素
    // ~230us,開機直接被 task watchdog 打死。canvas 是 TRUE_COLOR(無 alpha)
    // 且此處為不透明填滿,可直接對緩衝區做 16-bit 填充(lv_color_fill 在 IRAM)。
    lv_color_fill((lv_color_t *) img->data, lv_color_hex(0x040C08),
                  (uint32_t) RADAR_CANVAS * RADAR_CANVAS);
    lv_obj_invalidate(cv);   // 補回 lv_canvas_fill_bg 原本會做的失效標記
    if (map_show) {
      float coslat = cosf(lat0 * 3.14159265f / 180.0f);
      // 輪廓分層:海岸線最亮、國界中、州/省界最暗,近距離時線一多才分得出主次。
      // 分隔符(NAN,kind)的第二個值帶種類;舊 map_data.h 是 NAN,NAN,讀到 NAN
      // 一律當 0=海岸線,外觀與改版前完全相同。
      static const uint32_t MAP_KIND_COLOR[3] = {0xD8C878, 0x9A8B54, 0x685E38};
      lv_draw_line_dsc_t dsc;
      lv_draw_line_dsc_init(&dsc);
      dsc.color = lv_color_hex(MAP_KIND_COLOR[0]);   // 淡黃色輪廓線
      dsc.width = 1;
      dsc.opa = LV_OPA_COVER;
      float r2 = rng * rng;
      bool have_prev = false;
      lv_point_t prev{0, 0};
      float pd2 = 1e18f;
      for (int i = 0; i + 1 < MAP_OUTLINE_LEN; i += 2) {
        float la = MAP_OUTLINE[i], lo = MAP_OUTLINE[i + 1];
        if (isnan(la)) {
          have_prev = false;
          uint8_t kind = isnan(lo) ? 0 : (uint8_t) lo;
          if (kind > 2) kind = 2;
          dsc.color = lv_color_hex(MAP_KIND_COLOR[kind]);
          continue;
        }
        float e = (lo - lon0) * 111.320f * coslat;
        float n = (la - lat0) * 110.574f;
        float d2 = e * e + n * n;
        lv_point_t p;
        p.x = (lv_coord_t) (RADAR_CX + e / rng * (float) RADAR_R);
        p.y = (lv_coord_t) (RADAR_CX - n / rng * (float) RADAR_R);
        if (have_prev && (d2 <= r2 || pd2 <= r2)) {
          lv_point_t seg[2] = {prev, p};
          lv_canvas_draw_line(cv, seg, 2, &dsc);
        }
        prev = p;
        pd2 = d2;
        have_prev = true;
      }
    }
    if (cache) {
      memcpy(cache, img->data, BYTES);
      c_lat = lat0; c_lon = lon0; c_rng = rng; c_map = map_show;
    }
  }
  // 回波預混合:g_echo_buf 為 [color_lo][color_hi][alpha],逐像素混進底圖。
  // 只走 g_echo_x0/x1 記下的逐列範圍——降雨通常只佔畫面一小塊,沒下雨時整張
  // 全空,這樣就從「必掃 324,900 像素、讀 950KB PSRAM」變成只碰真的有資料的
  // 區段。底圖重建每次都做這一步(不進快取),所以省下的是每次的固定成本。
  if (echo_show && radar_bg::g_echo_buf) {
    lv_color_t *rows = (lv_color_t *) (void *) img->data;
    for (int y = 0; y < RADAR_CANVAS; y++) {
      const int xa = radar_bg::g_echo_x0[y], xb = radar_bg::g_echo_x1[y];
      if (xa > xb) continue;   // 整列無降雨:一次 PSRAM 讀取都不必
      const uint8_t *sp = radar_bg::g_echo_buf + ((size_t) y * RADAR_CANVAS + xa) * 3;
      lv_color_t *dst = rows + (size_t) y * RADAR_CANVAS + xa;
      for (int x = xa; x <= xb; x++, sp += 3, dst++) {
        if (sp[2] < 8) continue;   // 區段內的空隙,保留底圖
        lv_color_t fg;
        fg.full = (uint16_t) sp[0] | ((uint16_t) sp[1] << 8);
        *dst = lv_color_mix(fg, *dst, sp[2]);
      }
    }
  }
  // 十字線與 4 圈距離環:蓋在回波上,顏色/位置與原 widget 版一致
  lv_draw_line_dsc_t xd;
  lv_draw_line_dsc_init(&xd);
  xd.color = lv_color_hex(0x003820);
  xd.width = 1;
  lv_point_t xh[2] = {{0, RADAR_CX}, {RADAR_CANVAS, RADAR_CX}};
  lv_canvas_draw_line(cv, xh, 2, &xd);
  lv_point_t xv[2] = {{RADAR_CX, 0}, {RADAR_CX, RADAR_CANVAS}};
  lv_canvas_draw_line(cv, xv, 2, &xd);
  lv_draw_arc_dsc_t ad;
  lv_draw_arc_dsc_init(&ad);
  ad.color = lv_color_hex(0x006030);
  ad.width = 1;
  const lv_coord_t RINGS[4] = {RADAR_CX, (lv_coord_t)(RADAR_CX*3/4), (lv_coord_t)(RADAR_CX/2), (lv_coord_t)(RADAR_CX/4)};
  for (int k = 0; k < 4; k++)
    lv_canvas_draw_arc(cv, RADAR_CX, RADAR_CX, RINGS[k], 0, 360, &ad);
  // ---- ATC 靜態圖層(僅 ATC 模式,依 bitmask 逐層開關):空域/跑道+延伸線/機場/導航點 ----
  // 跟距離環一樣每次重建時畫、不進快取;重建只在切換或座標變更時發生,成本無感
  if (atc_layers) {
    float coslat = cosf(lat0 * 3.14159265f / 180.0f);
    float r2 = rng * rng;
    auto prj = [&](float la, float lo, float &e, float &n, lv_point_t &p) {
      e = (lo - lon0) * 111.320f * coslat;
      n = (la - lat0) * 110.574f;
      p.x = (lv_coord_t) (RADAR_CX + e / rng * (float) RADAR_R);
      p.y = (lv_coord_t) (RADAR_CX - n / rng * (float) RADAR_R);
    };
    // 空域邊界(最底):TMA/CTA 暗藍、CTR 類亮一階
    if (atc_layers & 1) {
    lv_draw_line_dsc_t asd;
    lv_draw_line_dsc_init(&asd);
    asd.width = 1;
    for (int a = 0; a < AIRSPACES_LEN; a++) {
      const MapAirspace &as = AIRSPACES[a];
      asd.color = lv_color_hex(as.cls == 0 ? 0x3A7A9A : 0x2A5070);
      bool hp = false;
      lv_point_t prev{0, 0};
      float pd2 = 1e18f;
      for (int k = 0; k < as.npts; k++) {
        float e, n;
        lv_point_t p;
        prj(AIRSPACE_PTS[as.off + 2 * k], AIRSPACE_PTS[as.off + 2 * k + 1], e, n, p);
        float d2 = e * e + n * n;
        if (hp && (d2 <= r2 || pd2 <= r2)) {
          lv_point_t s[2] = {prev, p};
          lv_canvas_draw_line(cv, s, 2, &asd);
        }
        prev = p; pd2 = d2; hp = true;
      }
    }
    }
    // 跑道延伸中線(虛線)+ 跑道本體(亮實線)
    if (atc_layers & 2) {
    lv_draw_line_dsc_t exd;
    lv_draw_line_dsc_init(&exd);
    exd.color = lv_color_hex(0x4A7A8A);
    exd.width = 1;
    lv_draw_line_dsc_t rwd;
    lv_draw_line_dsc_init(&rwd);
    rwd.color = lv_color_hex(0xD0E4EE);
    rwd.width = 2;
    for (int i = 0; i < RUNWAYS_LEN; i++) {
      const MapRunway &r = RUNWAYS[i];
      float e1, n1, e2, n2;
      lv_point_t p1, p2, x1, x2;
      prj(r.xlat1, r.xlon1, e1, n1, x1);
      prj(r.xlat2, r.xlon2, e2, n2, x2);
      if (e1 * e1 + n1 * n1 > r2 && e2 * e2 + n2 * n2 > r2) continue;
      // LVGL sw 渲染器的 dash 不支援斜線,延伸中線手動切段畫虛線(5px 畫 4px 空)
      float ddx = (float) (x2.x - x1.x), ddy = (float) (x2.y - x1.y);
      float dl = sqrtf(ddx * ddx + ddy * ddy);
      if (dl >= 2.0f) {
        for (float s = 0; s < dl; s += 9.0f) {
          float t0 = s / dl, t1 = (s + 5.0f) / dl;
          if (t1 > 1.0f) t1 = 1.0f;
          lv_point_t sx[2] = {
              {(lv_coord_t) (x1.x + ddx * t0), (lv_coord_t) (x1.y + ddy * t0)},
              {(lv_coord_t) (x1.x + ddx * t1), (lv_coord_t) (x1.y + ddy * t1)}};
          lv_canvas_draw_line(cv, sx, 2, &exd);
        }
      }
      prj(r.lat1, r.lon1, e1, n1, p1);
      prj(r.lat2, r.lon2, e2, n2, p2);
      lv_point_t sr[2] = {p1, p2};
      lv_canvas_draw_line(cv, sr, 2, &rwd);
    }
    }
    // 導航點:小空心三角 + 名稱(暗色,避免壓過航機)
    if (atc_layers & 8) {
    lv_draw_line_dsc_t fxd;
    lv_draw_line_dsc_init(&fxd);
    fxd.color = lv_color_hex(0x4A7A5A);
    fxd.width = 1;
    lv_draw_label_dsc_t fld;
    lv_draw_label_dsc_init(&fld);
    fld.font = lv_font_default();
    fld.color = lv_color_hex(0x50805E);
    for (int i = 0; i < FIXES_LEN; i++) {
      float e, n;
      lv_point_t p;
      prj(FIXES[i].lat, FIXES[i].lon, e, n, p);
      if (e * e + n * n > r2) continue;
      lv_point_t tri[4] = {{(lv_coord_t)(p.x), (lv_coord_t)(p.y - 3)},
                           {(lv_coord_t)(p.x + 3), (lv_coord_t)(p.y + 3)},
                           {(lv_coord_t)(p.x - 3), (lv_coord_t)(p.y + 3)},
                           {(lv_coord_t)(p.x), (lv_coord_t)(p.y - 3)}};
      lv_canvas_draw_line(cv, tri, 4, &fxd);
      lv_canvas_draw_text(cv, p.x + 5, p.y - 6, 60, &fld, FIXES[i].name);
    }
    }
    // 機場:實心小方塊 + ICAO 代碼(最上層)
    if (atc_layers & 4) {
    lv_draw_rect_dsc_t apd;
    lv_draw_rect_dsc_init(&apd);
    apd.bg_color = lv_color_hex(0xE0ECF4);
    apd.bg_opa = LV_OPA_COVER;
    lv_draw_label_dsc_t ald;
    lv_draw_label_dsc_init(&ald);
    ald.font = lv_font_default();
    ald.color = lv_color_hex(0x9AC8E0);
    for (int i = 0; i < AIRPORTS_LEN; i++) {
      float e, n;
      lv_point_t p;
      prj(AIRPORTS[i].lat, AIRPORTS[i].lon, e, n, p);
      if (e * e + n * n > r2) continue;
      lv_canvas_draw_rect(cv, p.x - 2, p.y - 2, 5, 5, &apd);
      lv_canvas_draw_text(cv, p.x + 5, p.y - 14, 60, &ald, AIRPORTS[i].icao);
    }
    }
  }
  lv_obj_invalidate(cv);
}

// ---- 三指下滑截圖:抓 RGB 面板 framebuffer → BMP,經 HTTP(:8081)供 HA downloader 下載 ----
#define SHOT_SWAP_BYTES 1   // 若截圖紅藍對調/顏色錯亂,改 1 重編譯
inline uint8_t *g_shot_buf = nullptr;        // 800*480*2 快照(PSRAM,首次截圖才配置)
inline char g_shot_path[40] = "";            // 寫進 SD 的檔名(不含目錄);空=沒寫到卡
                                             // 宣告在 RADAR_DISPLAY_RGB 守衛外:截圖停用的
                                             // 板子(P4 DSI)其狀態列 lambda 仍會讀這個變數
inline volatile bool g_shot_valid = false;

#if RADAR_DISPLAY_RGB
// 兩個 RGB 驅動的 panel handle 都叫 handle_ 且都是 protected,只有類別不同。
#if RADAR_DISPLAY_RGB == 1
using RadarRgbDisplay = esphome::rpi_dpi_rgb::RpiDpiRgb;
#else
using RadarRgbDisplay = esphome::mipi_rgb::MipiRgb;
#endif
// esp_lcd panel handle 在 ESPHome 元件裡是 protected,用衍生類取用(單 FB,拿到即當前畫面)
struct RpiSpy : public RadarRgbDisplay {
  static esp_lcd_panel_handle_t handle(RadarRgbDisplay *d) {
    return static_cast<RpiSpy *>(d)->handle_;
  }
};

// 24-bit BMP 標頭(row 3*W 對 800/1024 都是 4 的倍數,免 padding)。HTTP 與 SD 共用。
inline void shot_bmp_header(uint8_t hdr[54]) {
  memset(hdr, 0, 54);
  uint32_t img = (uint32_t) SCREEN_W * SCREEN_H * 3, sz = 54 + img, off = 54, ihsz = 40;
  int32_t w = SCREEN_W, h = SCREEN_H;
  uint16_t planes = 1, bpp = 24;
  hdr[0] = 'B'; hdr[1] = 'M';
  memcpy(hdr + 2, &sz, 4);  memcpy(hdr + 10, &off, 4);  memcpy(hdr + 14, &ihsz, 4);
  memcpy(hdr + 18, &w, 4);  memcpy(hdr + 22, &h, 4);
  memcpy(hdr + 26, &planes, 2);  memcpy(hdr + 28, &bpp, 2);  memcpy(hdr + 34, &img, 4);
}

// 把 g_shot_buf 的第 y 列(RGB565)轉成 BMP 的一列(24-bit BGR)。
inline void shot_bmp_row(int y, uint8_t *row) {
  const uint16_t *src = (const uint16_t *) g_shot_buf + (size_t) y * SCREEN_W;
  for (int x = 0; x < SCREEN_W; x++) {
    uint16_t v = src[x];
#if SHOT_SWAP_BYTES
    v = (uint16_t) ((v >> 8) | (v << 8));
#endif
    row[x * 3 + 0] = (uint8_t) ((v & 0x1F) << 3);          // B
    row[x * 3 + 1] = (uint8_t) (((v >> 5) & 0x3F) << 2);   // G
    row[x * 3 + 2] = (uint8_t) (((v >> 11) & 0x1F) << 3);  // R
  }
}

// ---- microSD(SPI):三指截圖另存一份到 TF 卡 ----
// 檔名 shot_YYYYMMDD_HHMMSS.bmp;SNTP 還沒對到時間就退回流水號。
// 掛載只嘗試一次(g_sd_tried),失敗就永遠走 HTTP 那條路,不每次重試拖慢截圖。
#if RADAR_SD_SPI
inline bool g_sd_ready = false;
inline bool g_sd_tried = false;

inline bool sd_mount() {
  if (g_sd_tried) return g_sd_ready;
  g_sd_tried = true;
  spi_bus_config_t bus = {};
  bus.mosi_io_num = RADAR_SD_MOSI;
  bus.miso_io_num = RADAR_SD_MISO;
  bus.sclk_io_num = RADAR_SD_CLK;
  bus.quadwp_io_num = -1;
  bus.quadhd_io_num = -1;
  bus.max_transfer_sz = 4096;
  esp_err_t e = spi_bus_initialize((spi_host_device_t) RADAR_SD_HOST, &bus, SPI_DMA_CH_AUTO);
  if (e != ESP_OK && e != ESP_ERR_INVALID_STATE) {   // INVALID_STATE = 這條 bus 已被初始化過
    ESP_LOGW("radar_sd", "spi_bus_initialize: %s", esp_err_to_name(e));
    return false;
  }
  sdmmc_host_t host = SDSPI_HOST_DEFAULT();
  host.slot = RADAR_SD_HOST;
  sdspi_device_config_t dev = SDSPI_DEVICE_CONFIG_DEFAULT();
  dev.host_id = (spi_host_device_t) RADAR_SD_HOST;
  dev.gpio_cs = SDSPI_SLOT_NO_CS;    // CS 在 CH422G EXIO4,由板檔的 switch 常拉低
  esp_vfs_fat_sdmmc_mount_config_t mnt = {};
  mnt.format_if_mount_failed = false;   // 不要動使用者的卡
  mnt.max_files = 2;
  mnt.allocation_unit_size = 16 * 1024;
  sdmmc_card_t *card = nullptr;
  e = esp_vfs_fat_sdspi_mount("/sdcard", &host, &dev, &mnt, &card);
  if (e != ESP_OK) {
    ESP_LOGW("radar_sd", "mount failed: %s (no card?)", esp_err_to_name(e));
    return false;
  }
  ESP_LOGI("radar_sd", "mounted %lluMB", ((uint64_t) card->csd.capacity * card->csd.sector_size) >> 20);
  g_sd_ready = true;
  return true;
}

inline bool sd_save_shot() {
  g_shot_path[0] = 0;
  if (!sd_mount()) return false;
  char path[64];
  time_t t = ::time(nullptr);   // ::  = 避開 esphome::time 命名空間
  struct tm tv;
  localtime_r(&t, &tv);
  if (tv.tm_year + 1900 >= 2024) {
    snprintf(path, sizeof(path), "/sdcard/shot_%04d%02d%02d_%02d%02d%02d.bmp",
             tv.tm_year + 1900, tv.tm_mon + 1, tv.tm_mday, tv.tm_hour, tv.tm_min, tv.tm_sec);
  } else {
    static int seq = 0;    // 時間還沒同步
    snprintf(path, sizeof(path), "/sdcard/shot_%03d.bmp", ++seq);
  }
  FILE *f = fopen(path, "wb");
  if (!f) { ESP_LOGW("radar_sd", "fopen %s failed", path); return false; }
  uint8_t hdr[54];
  shot_bmp_header(hdr);
  bool ok = fwrite(hdr, 1, 54, f) == 54;
  uint8_t *row = (uint8_t *) malloc((size_t) SCREEN_W * 3);
  if (row == nullptr) {
    ok = false;
  } else {
    for (int y = SCREEN_H - 1; ok && y >= 0; y--) {
      shot_bmp_row(y, row);
      ok = fwrite(row, 1, (size_t) SCREEN_W * 3, f) == (size_t) SCREEN_W * 3;
    }
    free(row);
  }
  fclose(f);
  if (!ok) { remove(path); ESP_LOGW("radar_sd", "write failed (card full?)"); return false; }
  snprintf(g_shot_path, sizeof(g_shot_path), "%s", strrchr(path, '/') + 1);
  ESP_LOGI("radar_sd", "saved %s", path);
  return true;
}
#else
inline bool sd_save_shot() { return false; }
#endif  // RADAR_SD_SPI

inline esp_err_t shot_http_get(httpd_req_t *req) {
  if (!g_shot_valid || !g_shot_buf) { httpd_resp_send_404(req); return ESP_OK; }
  const int H = SCREEN_H;
  uint8_t hdr[54];
  shot_bmp_header(hdr);
  httpd_resp_set_type(req, "image/bmp");
  httpd_resp_send_chunk(req, (const char *) hdr, 54);
  static uint8_t row[SCREEN_W * 3];
  for (int y = H - 1; y >= 0; y--) {         // BMP 由下往上
    shot_bmp_row(y, row);
    if (httpd_resp_send_chunk(req, (const char *) row, sizeof(row)) != ESP_OK)
      return ESP_FAIL;
  }
  httpd_resp_send_chunk(req, nullptr, 0);
  return ESP_OK;
}

inline bool screenshot_capture(RadarRgbDisplay *disp) {
  const size_t BYTES = (size_t) SCREEN_W * SCREEN_H * 2;
  if (!g_shot_buf) g_shot_buf = (uint8_t *) heap_caps_malloc(BYTES, MALLOC_CAP_SPIRAM);
  if (!g_shot_buf) return false;
  void *fb = nullptr;
  if (esp_lcd_rgb_panel_get_frame_buffer(RpiSpy::handle(disp), 1, &fb) != ESP_OK || !fb)
    return false;
  g_shot_valid = false;                      // 服務端讀到一半時避免撕裂判定
  memcpy(g_shot_buf, fb, BYTES);
  g_shot_valid = true;
  sd_save_shot();                            // 有卡就另存一份;失敗不影響 HTTP 這條路
  static httpd_handle_t srv = nullptr;       // 首次截圖才啟動 HTTP 服務
  if (!srv) {
    httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
    cfg.server_port = 8081;
    cfg.ctrl_port = 32780;                   // 避開 ESPHome web_server 的 httpd ctrl port
    cfg.max_open_sockets = 2;                // 預設 7 太浪費,一次只服務一個下載
    cfg.lru_purge_enable = true;             // 閒置連線自動回收,不佔 socket
    if (httpd_start(&srv, &cfg) == ESP_OK) {
      static const httpd_uri_t uri = {"/screenshot.bmp", HTTP_GET, shot_http_get, nullptr};
      httpd_register_uri_handler(srv, &uri);
    } else {
      srv = nullptr;
      return false;
    }
  }
  return true;
}
#else   // RADAR_DISPLAY_RGB == 0 : non-RGB bus (e.g. ESP32-P4 MIPI-DSI)
// Framebuffer screenshot relies on the parallel-RGB panel API; disable it on
// other display buses so the rest of the firmware still builds. Returns false
// so the caller reports "screenshot unavailable" instead of crashing.
inline bool screenshot_capture(void *disp) { (void) disp; return false; }
#endif  // RADAR_DISPLAY_RGB

// ---- 航班詳情:SQUAWK 一列 + 機型徽章 ----
// SQUAWK 三家來源都有;7500 劫機 / 7600 通訊失效 / 7700 一般緊急 → 轉紅,
// 呼應 ATC 告警配色。無值顯示 ----(例如剛出現、還沒收到 mode-A 碼)。
inline void radar_sq_line(lv_obj_t *lbl, const char *sq) {
  if (sq == nullptr || *sq == 0) sq = "----";
  char b[32];
  snprintf(b, sizeof(b), "SQUAWK %s", sq);
  lv_label_set_text(lbl, b);
  bool emerg = (strcmp(sq, "7500") == 0 || strcmp(sq, "7600") == 0 ||
                strcmp(sq, "7700") == 0);
  lv_obj_set_style_text_color(lbl, lv_color_hex(emerg ? 0xFF5030 : 0xD2E6D7), 0);
}

// ICAO 機型代碼的反白徽章。只有 airplanes.live / adsb.lol 提供機型,OpenSky 沒有,
// 所以無值時整個隱藏——否則會在呼號旁留一塊空的綠底。
inline void radar_type_badge(lv_obj_t *lbl, const char *ty) {
  if (ty == nullptr || *ty == 0) {
    lv_obj_add_flag(lbl, LV_OBJ_FLAG_HIDDEN);
    return;
  }
  lv_label_set_text(lbl, ty);
  lv_obj_clear_flag(lbl, LV_OBJ_FLAG_HIDDEN);
}

// ---- 系統資訊(i 鈕):CPU / RAM / PSRAM / FLASH / 運行時間 / API 額度 填入右下角六個 label ----
inline void radar_show_sysinfo(lv_obj_t *cs, lv_obj_t *route, lv_obj_t *l1,
                               lv_obj_t *l2, lv_obj_t *l3, lv_obj_t *l4, int rssi) {
  char b[48];
  lv_label_set_text(cs, "SYSTEM");
  snprintf(b, sizeof(b), "ESP32-S3 %uMHz   RSSI %d",
           (unsigned) esp_rom_get_cpu_ticks_per_us(), rssi);
  lv_label_set_text(route, b);
  snprintf(b, sizeof(b), "RAM   %4u / %4u KB",
           (unsigned) (heap_caps_get_free_size(MALLOC_CAP_INTERNAL) / 1024),
           (unsigned) (heap_caps_get_total_size(MALLOC_CAP_INTERNAL) / 1024));
  lv_label_set_text(l1, b);
  snprintf(b, sizeof(b), "PSRAM %4u / %4u KB",
           (unsigned) (heap_caps_get_free_size(MALLOC_CAP_SPIRAM) / 1024),
           (unsigned) (heap_caps_get_total_size(MALLOC_CAP_SPIRAM) / 1024));
  lv_label_set_text(l2, b);
  uint32_t fsz = 0;
  esp_flash_get_size(nullptr, &fsz);
  const esp_partition_t *ap = esp_ota_get_running_partition();
  snprintf(b, sizeof(b), "FLASH %u MB   APP %.1f MB", (unsigned) (fsz >> 20),
           ap ? ap->size / 1048576.0f : 0.0f);
  lv_label_set_text(l3, b);
  uint32_t up = (uint32_t) (esp_timer_get_time() / 1000000LL);
  if (radar_bg::g_last_src > 0)   // 免費來源(手選或 fallback):無額度,顯示來源名
    snprintf(b, sizeof(b), "UP %ud %02u:%02u   SRC %s", (unsigned) (up / 86400),
             (unsigned) (up / 3600 % 24), (unsigned) (up / 60 % 60),
             radar_bg::g_last_src == 2 ? "ADSB.LOL" : "A.LIVE");
  else if (radar_bg::g_os_remaining >= 0)
    snprintf(b, sizeof(b), "UP %ud %02u:%02u   API %d", (unsigned) (up / 86400),
             (unsigned) (up / 3600 % 24), (unsigned) (up / 60 % 60),
             radar_bg::g_os_remaining);   // OpenSky 當日剩餘呼叫額度
  else
    snprintf(b, sizeof(b), "UP %ud %02u:%02u   API ----", (unsigned) (up / 86400),
             (unsigned) (up / 3600 % 24), (unsigned) (up / 60 % 60));
  lv_label_set_text(l4, b);
}
