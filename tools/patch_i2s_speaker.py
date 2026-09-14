# PlatformIO pre-script: soft-patch stock i2s_audio speaker for ESP32-P4 / Tab5.
# Stock 2026.5+ treats ISR event-queue overflow as fatal (COMMAND_STOP + task restart),
# which kills RTTTL/voice on Tab5. Restore 2025.x "warn and continue" behavior.
#
# Wired via boards/m5stack_tab5.yaml → esphome.platformio_options.extra_scripts

Import("env")  # noqa: F821 — PlatformIO
from pathlib import Path


def _patch_file(path: Path, replacements: list[tuple[str, str]]) -> None:
    if not path.is_file():
        print(f"[patch_i2s] skip missing {path}")
        return
    text = path.read_text(encoding="utf-8")
    orig = text
    for old, new in replacements:
        if old not in text:
            if new.strip()[:40] in text:
                print(f"[patch_i2s] already patched {path.name}")
                return
            print(f"[patch_i2s] WARN pattern not found in {path.name}")
            return
        text = text.replace(old, new, 1)
    if text != orig:
        path.write_text(text, encoding="utf-8")
        print(f"[patch_i2s] patched {path}")


def patch_i2s_speaker(source=None, target=None, env=None):  # noqa: ARG001
    root = Path(env["PROJECT_DIR"])  # type: ignore[index]
    spk = root / "src" / "esphome" / "components" / "i2s_audio" / "speaker"

    _patch_file(
        spk / "i2s_audio_speaker.cpp",
        [
            (
                """  if (xQueueIsQueueFullFromISR(this_speaker->i2s_event_queue_)) {
    // Queue is full, so discard the oldest event. Once we drop a completion event, ``i2s_event_queue_``
    // and any per-buffer record queue maintained by the task are permanently desynced, so the task
    // must restart to recover. Set both ERR_DROPPED_EVENT (so loop() can log it) and COMMAND_STOP
    // (so the task bails immediately, closing the race where loop() could clear the error bit
    // before the task observes it).
    int64_t dummy;
    xQueueReceiveFromISR(this_speaker->i2s_event_queue_, &dummy, &need_yield1);
    xEventGroupSetBitsFromISR(this_speaker->event_group_,
                              SpeakerEventGroupBits::ERR_DROPPED_EVENT | SpeakerEventGroupBits::COMMAND_STOP,
                              &need_yield2);
  }""",
                """  if (xQueueIsQueueFullFromISR(this_speaker->i2s_event_queue_)) {
    // Tab5/P4: discard oldest completion and continue (2025.x). Do NOT COMMAND_STOP —
    // fatal restart kills short RTTTL beeps and voice clips under LVGL load.
    int64_t dummy;
    xQueueReceiveFromISR(this_speaker->i2s_event_queue_, &dummy, &need_yield1);
    xEventGroupSetBitsFromISR(this_speaker->event_group_, SpeakerEventGroupBits::ERR_DROPPED_EVENT,
                              &need_yield2);
  }""",
            ),
            (
                """    if (event_group_bits & SpeakerEventGroupBits::ERR_DROPPED_EVENT) {
      ESP_LOGE(TAG, "ISR event queue overflow, restarting speaker task to recover timestamp sync");
    }""",
                """    if (event_group_bits & SpeakerEventGroupBits::ERR_DROPPED_EVENT) {
      ESP_LOGW(TAG, "ISR event queue overflow (continuing; timestamps may drift)");
    }""",
            ),
        ],
    )

    _patch_file(
        spk / "i2s_audio_speaker_standard.cpp",
        [
            (
                "static constexpr size_t I2S_EVENT_QUEUE_COUNT = DMA_BUFFERS_COUNT * 2;",
                "static constexpr size_t I2S_EVENT_QUEUE_COUNT = DMA_BUFFERS_COUNT * 8;",
            ),
            (
                """        if (xQueueReceive(this->write_records_queue_, &real_frames, 0) != pdTRUE) {
          // Should never happen: would indicate the lockstep invariant is broken.
          ESP_LOGV(TAG, "Event without matching write record");
          xEventGroupSetBits(this->event_group_, SpeakerEventGroupBits::ERR_LOCKSTEP_DESYNC);
          lockstep_broken = true;
          break;
        }""",
                """        if (xQueueReceive(this->write_records_queue_, &real_frames, 0) != pdTRUE) {
          // Soft-dropped ISR events can leave an unpaired timestamp; skip instead of fatal restart.
          ESP_LOGW(TAG, "Event without matching write record (skip)");
          continue;
        }""",
            ),
        ],
    )


# Run once at script load (sources already copied by ESPHome before pio starts)
patch_i2s_speaker(env=env)  # noqa: F821
