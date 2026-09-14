"""Tab5: soft-patch stock i2s_audio at compile time without vendoring the whole component."""

from pathlib import Path

import esphome.config_validation as cv
from esphome.components.esp32 import add_idf_sdkconfig_option
from esphome.core import CORE

CODEOWNERS = ["@local"]
DEPENDENCIES = ["esp32"]

CONFIG_SCHEMA = cv.Schema({})


async def to_code(config):
    # Stock i2s_audio forces IRAM-safe I2S ISR; on Tab5/P4 that can starve internal SRAM
    # so FreeRTOS Timer fails: vApplicationGetTimerTaskMemory (pxStackBufferTemp != NULL).
    add_idf_sdkconfig_option("CONFIG_I2S_ISR_IRAM_SAFE", False)

    script = Path(__file__).resolve().parents[2] / "tools" / "patch_i2s_speaker.py"
    if not script.is_file():
        raise cv.Invalid(f"missing i2s patch script: {script}")
    CORE.platformio_options.setdefault("extra_scripts", [])
    entry = f"pre:{script.as_posix()}"
    if entry not in CORE.platformio_options["extra_scripts"]:
        CORE.platformio_options["extra_scripts"].append(entry)
