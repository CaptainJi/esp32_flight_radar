#pragma once
// Tab5 板载喇叭:对齐 M5Unified::_speaker_enabled_cb_tab5 的 ES8388 初始化。
// ESPHome es8388::setup() 不写 DACPOWER / OUT 音量 / mixer(0xB8),仅靠它会静音。
#include "esphome/components/i2c/i2c.h"
#include "esphome/core/log.h"

namespace tab5_audio {

static const char *const TAG = "tab5_audio";
static constexpr uint8_t kEs8388Addr = 0x10;

inline bool wr(esphome::i2c::I2CBus *bus, uint8_t reg, uint8_t val) {
  uint8_t buf[2] = {reg, val};
  auto err = bus->write(kEs8388Addr, buf, 2);
  return err == esphome::i2c::ERROR_OK;
}

// 与 M5Unified enabled_bulk_data 一致(reg 为十进制地址)
inline bool es8388_speaker_on(esphome::i2c::I2CBus *bus) {
  if (bus == nullptr) return false;
  const uint8_t seq[][2] = {
      {0, 0x80},  // RESET / CSM POWER ON
      {0, 0x00},
      {0, 0x00},
      {0, 0x0E},
      {1, 0x00},
      {2, 0x0A},   // CHIPPOWER: power up all
      {3, 0xFF},   // ADCPOWER: down
      {4, 0x3C},   // DACPOWER: DAC + LOUT1/ROUT1/LOUT2/ROUT2
      {5, 0x00},
      {6, 0x00},
      {7, 0x7C},   // VSEL
      {8, 0x00},   // I2S slave
      {23, 0x18},  // I2S 16-bit
      // DACCONTROL2: 0x02 = MCLK/LRCK 256 (single-speed 8–50kHz; 与 speaker mclk_multiple:256 对齐)
      // 注:M5Unified 写 0x00(=128) 配 48k;16k 语音/RTTTL 用 256 更符合 datasheet
      {24, 0x02},
      {25, 0x20},  // DAC unmute
      {26, 0x00},  // LDACVOL max
      {27, 0x00},  // RDACVOL max
      {28, 0x08},  // click-free
      {29, 0x00},
      {38, 0x00},  // DAC CTRL16
      {39, 0xB8},  // LEFT mix
      {42, 0xB8},  // RIGHT mix
      {43, 0x08},  // ADC/DAC separate
      {45, 0x00},  // VREF 1.5k
      {46, 0x21},  // LOUT1VOL
      {47, 0x21},  // ROUT1VOL
      {48, 0x21},  // LOUT2VOL
      {49, 0x21},  // ROUT2VOL
  };
  for (const auto &p : seq) {
    if (!wr(bus, p[0], p[1])) {
      ESP_LOGE(TAG, "ES8388 write 0x%02X failed", p[0]);
      return false;
    }
  }
  ESP_LOGI(TAG, "ES8388 speaker path ready (M5Unified seq)");
  return true;
}

}  // namespace tab5_audio
