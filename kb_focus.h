#pragma once
// 物理键盘焦点:仅 Tab5 + A164 时生效;其他板型为空操作
#include <lvgl.h>
#include <cstddef>
#ifdef TAB5_KB
#include "tab5_kb.h"
#include "kb_router.h"
inline void radar_kb_focus(lv_obj_t *ta) { tab5_kb::focus(ta); }
inline void radar_kb_clear_focus() { tab5_kb::clear_focus(); }
inline void radar_kb_flush_pending() { tab5_kb::flush_pending(); }
inline bool radar_kb_pop_cmd(char *out, size_t n) { return tab5_kb::pop_cmd(out, n); }
inline void radar_kb_led_sync(bool call_on, bool talk_on, bool help_on) {
  tab5_kb::led_sync(call_on, talk_on, help_on);
}
#else
inline void radar_kb_focus(lv_obj_t *ta) { (void) ta; }
inline void radar_kb_clear_focus() {}
inline void radar_kb_flush_pending() {}
inline bool radar_kb_pop_cmd(char *out, size_t n) {
  (void) out;
  (void) n;
  return false;
}
inline void radar_kb_led_sync(bool call_on, bool talk_on, bool help_on) {
  (void) call_on;
  (void) talk_on;
  (void) help_on;
}
#endif
