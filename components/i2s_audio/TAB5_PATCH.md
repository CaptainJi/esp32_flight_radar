# Tab5 / ESP32-P4 i2s_audio

**Do not** vendor full `i2s_audio` via `external_components` on Tab5 — it previously caused
boot loop / black screen:

`assert failed: vApplicationGetTimerTaskMemory ... (pxStackBufferTemp != NULL)`

Use instead:
- `components/tab5_i2s_fix` — disables `CONFIG_I2S_ISR_IRAM_SAFE`, registers patch script
- `tools/patch_i2s_speaker.py` — soft-handles ISR overflow (no fatal speaker restart)

Reference copies under `components/i2s_audio/` are not wired.
