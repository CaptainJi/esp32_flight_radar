#pragma once
// RADIO 通话回报排版:Roboto + Noto CJK 混排时,汉字与英文/数字紧贴会显得参差。
// 在 CJK ↔ ASCII 字母数字边界插入空格,并在句号后换行,方便小框阅读。

#include <cstdint>
#include <string>

namespace radar_ui {

inline bool is_ascii_alnum(unsigned char c) {
  return (c >= '0' && c <= '9') || (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z');
}

inline int utf8_len(unsigned char c) {
  if (c < 0x80) return 1;
  if ((c & 0xE0) == 0xC0) return 2;
  if ((c & 0xF0) == 0xE0) return 3;
  if ((c & 0xF8) == 0xF0) return 4;
  return 1;
}

inline uint32_t utf8_cp(const char *p, int n) {
  auto u = [](char ch) -> uint32_t { return (uint32_t) (unsigned char) ch; };
  if (n == 1) return u(p[0]);
  if (n == 2) return ((u(p[0]) & 0x1Fu) << 6) | (u(p[1]) & 0x3Fu);
  if (n == 3)
    return ((u(p[0]) & 0x0Fu) << 12) | ((u(p[1]) & 0x3Fu) << 6) | (u(p[2]) & 0x3Fu);
  if (n == 4)
    return ((u(p[0]) & 0x07u) << 18) | ((u(p[1]) & 0x3Fu) << 12) |
           ((u(p[2]) & 0x3Fu) << 6) | (u(p[3]) & 0x3Fu);
  return u(p[0]);
}

inline bool is_cjk_cp(uint32_t cp) {
  return (cp >= 0x4E00 && cp <= 0x9FFF) || (cp >= 0x3400 && cp <= 0x4DBF) ||
         (cp >= 0xF900 && cp <= 0xFAFF) || (cp >= 0x3000 && cp <= 0x303F) ||
         (cp >= 0xFF01 && cp <= 0xFF60);
}

enum class ChKind : uint8_t { None, Ascii, Cjk, Other };

inline std::string pretty_mixed(const std::string &in) {
  std::string out;
  out.reserve(in.size() + 24);
  ChKind prev = ChKind::None;
  for (size_t i = 0; i < in.size();) {
    unsigned char c = (unsigned char) in[i];
    int n = utf8_len(c);
    if (i + (size_t) n > in.size()) n = 1;

    ChKind k = ChKind::Other;
    uint32_t cp = 0;
    if (n == 1 && is_ascii_alnum(c)) {
      k = ChKind::Ascii;
    } else if (n >= 2) {
      cp = utf8_cp(in.data() + i, n);
      if (is_cjk_cp(cp)) k = ChKind::Cjk;
    }

    if ((prev == ChKind::Ascii && k == ChKind::Cjk) ||
        (prev == ChKind::Cjk && k == ChKind::Ascii)) {
      out.push_back(' ');
    }

    out.append(in, i, (size_t) n);

    if (n == 1 && c == ',' && i + 1 < in.size() && in[i + 1] != ' ' &&
        in[i + 1] != '\n') {
      out.push_back(' ');
    }

    // 句号后若还有正文,换行(避免「。当前」黏成一行)
    if (n == 3 && cp == 0x3002 /* 。 */ && i + (size_t) n < in.size() &&
        in[i + (size_t) n] != '\n') {
      out.push_back('\n');
      prev = ChKind::None;
      i += (size_t) n;
      continue;
    }

    if (n == 1 && (c == ' ' || c == '\n'))
      prev = ChKind::None;
    else
      prev = k;
    i += (size_t) n;
  }
  return out;
}

}  // namespace radar_ui
