#pragma once
// 物理键盘焦点:仅 Tab5 + A164 时生效;其他板型为空操作
#include <lvgl.h>
#ifdef TAB5_KB
#include "tab5_kb.h"
inline void radar_kb_focus(lv_obj_t *ta) { tab5_kb::focus(ta); }
inline void radar_kb_clear_focus() { tab5_kb::clear_focus(); }
inline void radar_kb_flush_pending() { tab5_kb::flush_pending(); }
inline bool radar_kb_want_talk() { return tab5_kb::consume_want_talk(); }
#else
inline void radar_kb_focus(lv_obj_t *ta) { (void) ta; }
inline void radar_kb_clear_focus() {}
inline void radar_kb_flush_pending() {}
inline bool radar_kb_want_talk() { return false; }
#endif
