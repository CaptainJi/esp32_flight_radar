#pragma once
// Tab5 Keyboard (SKU A164) — Ext.Port1 I2C 字符模式 → LVGL textarea
// 协议见官方 I2C Protocol;引脚 SDA=G0 SCL=G1 INT=G50;地址 0x6D
#include "esphome/components/i2c/i2c_bus.h"
#include "esphome/core/log.h"
#include <lvgl.h>
#include <cstring>

namespace tab5_kb {

static const char *const TAG = "tab5_kb";
static constexpr uint8_t ADDR = 0x6D;
static constexpr uint8_t REG_INT_CFG = 0x00;
static constexpr uint8_t REG_INT_STA = 0x01;
static constexpr uint8_t REG_EVENT_NUM = 0x02;
static constexpr uint8_t REG_MODE = 0x10;
static constexpr uint8_t REG_CHAR_LEN = 0x40;
static constexpr uint8_t REG_CHAR_BASE = 0x50;
static constexpr uint8_t REG_VERSION = 0xFE;
static constexpr uint8_t MODE_STRING = 2;

inline esphome::i2c::I2CBus *bus_ = nullptr;
inline lv_obj_t *ta_ = nullptr;
inline lv_obj_t *soft_kb_a_ = nullptr;
inline lv_obj_t *soft_kb_b_ = nullptr;
inline bool ready_ = false;
inline volatile bool want_talk_ = false;
inline char pending_[48];
inline uint8_t pending_len_ = 0;

inline void focus(lv_obj_t *ta) { ta_ = ta; }
inline void clear_focus() { ta_ = nullptr; }

inline void bind_soft_kbs(lv_obj_t *a, lv_obj_t *b) {
  soft_kb_a_ = a;
  soft_kb_b_ = b;
}

inline bool consume_want_talk() {
  if (!want_talk_) return false;
  want_talk_ = false;
  return true;
}

inline int icmp(const char *a, const char *b) {
  while (*a && *b) {
    unsigned char ca = (unsigned char) *a++;
    unsigned char cb = (unsigned char) *b++;
    if (ca >= 'A' && ca <= 'Z') ca = (unsigned char) (ca - 'A' + 'a');
    if (cb >= 'A' && cb <= 'Z') cb = (unsigned char) (cb - 'A' + 'a');
    if (ca != cb) return (int) ca - (int) cb;
  }
  return (int) (unsigned char) *a - (int) (unsigned char) *b;
}

// A164 字符模式固件直接推送键名字符串(见 M5Tab5-Keyboard-Internal-FW
// user_keyboard_handle.c key_value_map),不是 \b/\n 等控制符。
inline char named_to_ctrl(const char *s) {
  if (s == nullptr || s[0] == '\0') return 0;
  if (icmp(s, "backspace") == 0) return '\b';
  if (icmp(s, "del") == 0 || icmp(s, "delete") == 0) return 0x7F;
  if (icmp(s, "tab") == 0) return '\t';
  if (icmp(s, "enter") == 0) return '\n';
  if (icmp(s, "esc") == 0 || icmp(s, "escape") == 0) return 0x1B;
  if (icmp(s, "left") == 0) return 0x14;
  if (icmp(s, "right") == 0) return 0x13;
  if (icmp(s, "up") == 0) return 0x11;
  if (icmp(s, "down") == 0) return 0x12;
  // 固件侧已过滤,兜底忽略
  if (icmp(s, "sym") == 0 || icmp(s, "aa") == 0 || icmp(s, "ctrl") == 0 ||
      icmp(s, "alt") == 0)
    return 0x1B;
  return 0;
}

inline void inject_ctrl(lv_obj_t *ta, char c) {
  if (ta == nullptr || c == 0) return;
  if (c == '\b') {
    lv_textarea_delete_char(ta);
  } else if (c == '\n' || c == '\r') {
    if (lv_textarea_get_one_line(ta)) return;
    lv_textarea_add_char(ta, '\n');
  } else if (c == 0x7F) {
    lv_textarea_delete_char_forward(ta);
  } else if (c == 0x14) {
    lv_textarea_cursor_left(ta);
  } else if (c == 0x13) {
    lv_textarea_cursor_right(ta);
  } else if (c == 0x11) {
    lv_textarea_cursor_up(ta);
  } else if (c == 0x12) {
    lv_textarea_cursor_down(ta);
  } else if (c == '\t') {
    lv_textarea_add_char(ta, ' ');
    lv_textarea_add_char(ta, ' ');
  } else if (c == 0x02) {
    lv_textarea_set_cursor_pos(ta, 0);
  } else if (c == 0x03) {
    lv_textarea_set_cursor_pos(ta, LV_TEXTAREA_CURSOR_LAST);
  } else if (c == 0x1B) {
    // Esc / modifiers — ignore
  } else {
    char one[2] = {c, '\0'};
    lv_textarea_add_text(ta, one);
  }
}

inline void inject(lv_obj_t *ta, const char *val) {
  if (ta == nullptr || val == nullptr || val[0] == '\0') return;
  // 多字节键名优先(backspace/tab/enter/...)
  char ctrl = named_to_ctrl(val);
  if (ctrl != 0) {
    inject_ctrl(ta, ctrl);
    return;
  }
  // 单字节控制符(兼容 pending 规范化后的队列)
  if (val[1] == '\0') {
    const unsigned char c = (unsigned char) val[0];
    if (c < 0x20 || c == 0x7F) {
      inject_ctrl(ta, (char) c);
      return;
    }
  }
  lv_textarea_add_text(ta, val);
}

inline void queue_pending(const char *val) {
  if (val == nullptr || val[0] == '\0') return;
  // 功能键压成单控制符,避免 pending 拼接后无法识别 "backspace"
  char ctrl = named_to_ctrl(val);
  if (ctrl != 0) {
    if (pending_len_ + 1 >= sizeof(pending_)) return;
    pending_[pending_len_++] = ctrl;
    pending_[pending_len_] = '\0';
    return;
  }
  size_t n = strlen(val);
  if (pending_len_ + n >= sizeof(pending_)) return;
  memcpy(pending_ + pending_len_, val, n);
  pending_len_ = (uint8_t) (pending_len_ + n);
  pending_[pending_len_] = '\0';
}

inline void flush_pending() {
  if (ta_ == nullptr || pending_len_ == 0) {
    pending_len_ = 0;
    pending_[0] = '\0';
    return;
  }
  // pending 已规范化:可打印串 + 单字节控制符
  for (uint8_t i = 0; i < pending_len_;) {
    unsigned char c = (unsigned char) pending_[i];
    if (c < 0x20 || c == 0x7F) {
      inject_ctrl(ta_, (char) c);
      i++;
    } else {
      char one[2] = {(char) c, '\0'};
      lv_textarea_add_text(ta_, one);
      i++;
    }
  }
  pending_len_ = 0;
  pending_[0] = '\0';
}

inline bool wr(uint8_t reg, uint8_t val) {
  if (bus_ == nullptr) return false;
  uint8_t buf[2] = {reg, val};
  return bus_->write(ADDR, buf, 2) == esphome::i2c::ERROR_OK;
}

inline bool rd(uint8_t reg, uint8_t *out, size_t n) {
  if (bus_ == nullptr || out == nullptr || n == 0) return false;
  return bus_->write_readv(ADDR, &reg, 1, out, n) == esphome::i2c::ERROR_OK;
}

inline lv_obj_t *resolve_ta() {
  if (ta_ != nullptr) return ta_;
  auto try_kb = [](lv_obj_t *kb) -> lv_obj_t * {
    if (kb == nullptr) return nullptr;
    if (lv_obj_has_flag(kb, LV_OBJ_FLAG_HIDDEN)) return nullptr;
    return lv_keyboard_get_textarea(kb);
  };
  if (auto *t = try_kb(soft_kb_a_)) return t;
  if (auto *t = try_kb(soft_kb_b_)) return t;
  return nullptr;
}

inline void setup(esphome::i2c::I2CBus *bus) {
  bus_ = bus;
  ready_ = false;
  if (bus_ == nullptr) return;
  uint8_t ver = 0;
  if (!rd(REG_VERSION, &ver, 1)) {
    ESP_LOGW(TAG, "A164 not on 0x6D — physical keyboard off");
    return;
  }
  wr(REG_MODE, MODE_STRING);
  wr(REG_INT_CFG, 0x04);   // 仅字符模式中断
  wr(REG_EVENT_NUM, 0);    // 清队列
  wr(REG_INT_STA, 0);
  ready_ = true;
  ESP_LOGI(TAG, "A164 ready fw=0x%02X STRING mode", ver);
}

inline void poll() {
  if (!ready_ || bus_ == nullptr) return;

  uint8_t sta = 0;
  if (!rd(REG_INT_STA, &sta, 1)) return;
  if ((sta & 0x04) == 0) return;

  uint8_t n = 0;
  if (!rd(REG_EVENT_NUM, &n, 1) || n == 0 || n > 32) {
    wr(REG_INT_STA, 0);
    return;
  }

  lv_obj_t *ta = resolve_ta();
  while (n-- > 0) {
    uint8_t len = 0;
    if (!rd(REG_CHAR_LEN, &len, 1) || len == 0 || len > 15) break;
    uint8_t buf[16];
    if (!rd(REG_CHAR_BASE, buf, (size_t) len + 1)) break;
    char s[16];
    memcpy(s, &buf[1], len);
    s[len] = '\0';
    // modifier: bit0=Ctrl bit2=Alt — 普通输入才写入文本框
    if ((buf[0] & 0x05) != 0) continue;
    if (ta != nullptr) {
      inject(ta, s);
    } else {
      // RADIO 面板无输入框:缓存首键并请求打开 TALK
      queue_pending(s);
      want_talk_ = true;
    }
  }
  wr(REG_INT_STA, 0);
}

}  // namespace tab5_kb
