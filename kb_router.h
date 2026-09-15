#pragma once
// Tab5 A164 键盘命令分类 + 工具/CALL 钮焦点环(Phase 0–2)
// 业务动作在 common/core.yaml 的 kb_drain 中执行(可访问 id())
#include <cstdint>
#include <cstring>
#include <lvgl.h>

namespace kb_router {

static constexpr uint32_t FOCUS_BORDER = 0xE8A020;  // 选中:琥珀边
static constexpr uint32_t FOCUS_TEXT = 0xE8A020;    // 选中:琥珀字
static constexpr uint32_t ON_FILL = 0x00C060;       // 开启:绿底
static constexpr uint32_t ON_TEXT = 0x04180C;       // 开启:黑字
static constexpr uint32_t OFF_BORDER = 0x00A050;    // 关闭:绿边
static constexpr uint32_t OFF_TEXT = 0x00C060;      // 关闭:绿字

enum class Key : uint8_t {
  None = 0,
  Up,
  Down,
  Left,
  Right,
  Enter,
  Esc,
  Tab,
  Plus,
  Minus,
  Space,
  Digit,  // ch = '0'..'9'
  Char,   // ch = 'a'..'z'
};

struct Ev {
  Key key = Key::None;
  char ch = 0;
};

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

inline Ev classify(const char *s) {
  Ev e;
  if (s == nullptr || s[0] == '\0') return e;
  if (icmp(s, "up") == 0) {
    e.key = Key::Up;
    return e;
  }
  if (icmp(s, "down") == 0) {
    e.key = Key::Down;
    return e;
  }
  if (icmp(s, "left") == 0) {
    e.key = Key::Left;
    return e;
  }
  if (icmp(s, "right") == 0) {
    e.key = Key::Right;
    return e;
  }
  if (icmp(s, "enter") == 0) {
    e.key = Key::Enter;
    return e;
  }
  if (icmp(s, "esc") == 0 || icmp(s, "escape") == 0) {
    e.key = Key::Esc;
    return e;
  }
  if (icmp(s, "tab") == 0) {
    e.key = Key::Tab;
    return e;
  }
  if (icmp(s, "backspace") == 0 || icmp(s, "del") == 0 || icmp(s, "delete") == 0)
    return e;  // 导航层忽略退格
  if (icmp(s, "sym") == 0 || icmp(s, "aa") == 0 || icmp(s, "ctrl") == 0 ||
      icmp(s, "alt") == 0)
    return e;

  // 单字符 / 已规范化的控制符
  if (s[1] == '\0') {
    unsigned char c = (unsigned char) s[0];
    if (c == 0x11) {
      e.key = Key::Up;
      return e;
    }
    if (c == 0x12) {
      e.key = Key::Down;
      return e;
    }
    if (c == 0x14) {
      e.key = Key::Left;
      return e;
    }
    if (c == 0x13) {
      e.key = Key::Right;
      return e;
    }
    if (c == '\n' || c == '\r') {
      e.key = Key::Enter;
      return e;
    }
    if (c == 0x1B) {
      e.key = Key::Esc;
      return e;
    }
    if (c == '\t') {
      e.key = Key::Tab;
      return e;
    }
    if (c == '+' || c == '=') {
      e.key = Key::Plus;
      return e;
    }
    if (c == '-' || c == '_') {
      e.key = Key::Minus;
      return e;
    }
    if (c == ' ') {
      e.key = Key::Space;
      return e;
    }
    if (c >= '0' && c <= '9') {
      e.key = Key::Digit;
      e.ch = (char) c;
      return e;
    }
    if (c >= 'A' && c <= 'Z') c = (unsigned char) (c - 'A' + 'a');
    if (c >= 'a' && c <= 'z') {
      e.key = Key::Char;
      e.ch = (char) c;
      return e;
    }
  }
  return e;
}

inline void set_tool_ring(lv_obj_t *btn, lv_obj_t *lbl, bool focused,
                          bool force_on = false) {
  if (btn == nullptr) return;
  const bool checked =
      force_on || lv_obj_has_state(btn, LV_STATE_CHECKED);
  // 脏检查:状态未变则跳过 style 写入(避免每秒 invalidate)
  uint8_t stamp = (uint8_t) ((focused ? 4 : 0) | (checked ? 2 : 0) | 1);
  void *prev = lv_obj_get_user_data(btn);
  if ((uintptr_t) prev == (uintptr_t) stamp) return;
  lv_obj_set_user_data(btn, (void *) (uintptr_t) stamp);

  if (focused) {
    // 选中:琥珀边(+略加粗);字琥珀。开启时仍保留绿底。
    lv_obj_set_style_border_color(btn, lv_color_hex(FOCUS_BORDER), 0);
    lv_obj_set_style_border_width(btn, 3, 0);
    if (lbl)
      lv_obj_set_style_text_color(lbl, lv_color_hex(FOCUS_TEXT), 0);
  } else if (checked) {
    lv_obj_set_style_border_color(btn, lv_color_hex(ON_FILL), 0);
    lv_obj_set_style_border_width(btn, 2, 0);
    if (lbl)
      lv_obj_set_style_text_color(lbl, lv_color_hex(ON_TEXT), 0);
  } else {
    lv_obj_set_style_border_color(btn, lv_color_hex(OFF_BORDER), 0);
    lv_obj_set_style_border_width(btn, 2, 0);
    if (lbl)
      lv_obj_set_style_text_color(lbl, lv_color_hex(OFF_TEXT), 0);
  }
}

inline void apply_tool_rings(lv_obj_t *const *btns, lv_obj_t *const *lbls, int n,
                             int focus_idx, bool tool_mode) {
  for (int i = 0; i < n; i++) {
    lv_obj_t *lbl = (lbls != nullptr) ? lbls[i] : nullptr;
    set_tool_ring(btns[i], lbl, tool_mode && focus_idx == i);
  }
}

// CALL 层 9 项:短语1-4 / 语种 / STATIC / CABIN / TALK / END
static constexpr int CALL_FOCUS_N = 9;

// 主界面导航:0=飞机列表 1..6=MAP..SYS 7=CALL 徽章
static constexpr int NAV_AC = 0;
static constexpr int NAV_TOOL0 = 1;
static constexpr int NAV_CALL = 7;

inline void apply_call_rings(lv_obj_t *const *btns, lv_obj_t *const *lbls,
                             int focus_idx, bool active) {
  for (int i = 0; i < CALL_FOCUS_N; i++) {
    lv_obj_t *lbl = (lbls != nullptr) ? lbls[i] : nullptr;
    // TALK(7) 本身是实心绿钮,未选中时按「开启」样式还原
    const bool force_on = (i == 7);
    set_tool_ring(btns[i], lbl, active && focus_idx == i, force_on);
  }
}

// CALL 面板二维邻接(接近 Windows 对话框方向键):
//   [4 lang]              [8 END]
//   [0 p1 ]  [1 p2 ]
//   [2 p3 ]  [3 p4 ]
//   [5 rfx]  [6 fbg]
//   [7 talk            ]
inline int call_move(int i, Key dir) {
  if (i < 0 || i >= CALL_FOCUS_N) i = 0;
  switch (dir) {
    case Key::Left:
      switch (i) {
        case 1:
          return 0;
        case 3:
          return 2;
        case 6:
          return 5;
        case 8:
          return 4;
        case 7:
          return 5;
        default:
          return i;
      }
    case Key::Right:
      switch (i) {
        case 0:
          return 1;
        case 2:
          return 3;
        case 4:
          return 8;
        case 5:
          return 6;
        case 7:
          return 6;
        default:
          return i;
      }
    case Key::Up:
      switch (i) {
        case 0:
          return 4;
        case 1:
          return 8;
        case 2:
          return 0;
        case 3:
          return 1;
        case 5:
          return 2;
        case 6:
          return 3;
        case 7:
          return 5;
        default:
          return i;
      }
    case Key::Down:
      switch (i) {
        case 4:
          return 0;
        case 8:
          return 1;
        case 0:
          return 2;
        case 1:
          return 3;
        case 2:
          return 5;
        case 3:
          return 6;
        case 5:
        case 6:
          return 7;
        default:
          return i;
      }
    default:
      return i;
  }
}

// 主界面方向键:工具横排 + 下方 CALL;飞机区↑↓换机
inline int nav_move(int idx, Key dir, bool call_visible) {
  const int max_i = call_visible ? NAV_CALL : (NAV_CALL - 1);
  if (idx < NAV_AC) idx = NAV_AC;
  if (idx > max_i) idx = max_i;

  switch (dir) {
    case Key::Left:
      if (idx == NAV_AC) return call_visible ? NAV_CALL : (NAV_TOOL0 + 5);
      if (idx == NAV_TOOL0) return NAV_AC;
      if (idx == NAV_CALL) return NAV_TOOL0 + 5;  // SYS
      return idx - 1;
    case Key::Right:
      if (idx == NAV_AC) return NAV_TOOL0;
      if (idx >= NAV_TOOL0 && idx < NAV_TOOL0 + 5) return idx + 1;
      if (idx == NAV_TOOL0 + 5) return call_visible ? NAV_CALL : NAV_AC;
      if (idx == NAV_CALL) return NAV_AC;
      return idx;
    case Key::Up:
      if (idx == NAV_AC) return NAV_AC;  // 飞机列表由上层处理选机
      if (idx >= NAV_TOOL0 && idx <= NAV_TOOL0 + 5) return NAV_AC;
      if (idx == NAV_CALL) return NAV_TOOL0 + 3;  // 回到 ATC 附近
      return idx;
    case Key::Down:
      if (idx == NAV_AC) return NAV_TOOL0;
      if (idx >= NAV_TOOL0 && idx <= NAV_TOOL0 + 5)
        return call_visible ? NAV_CALL : NAV_AC;
      return idx;
    default:
      return idx;
  }
}

inline int nav_tab(int idx, int delta, bool call_visible) {
  const int n = call_visible ? 8 : 7;  // 0..7 或 0..6
  if (idx < 0 || idx >= n) idx = 0;
  return (idx + delta % n + n) % n;
}

}  // namespace kb_router
