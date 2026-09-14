"""无线电特效 + 飞行舱背景音（纯 PCM 后处理，不依赖外部素材）。"""

from __future__ import annotations

import math
import os
import random
import struct
from typing import Iterable


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name, "1" if default else "0").strip().lower()
    return v in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)).strip())
    except (TypeError, ValueError):
        return default


def radio_fx_enabled(override: bool | None = None) -> bool:
    if override is not None:
        return override
    return _env_bool("RADIO_FX", False)


def flight_bg_enabled(override: bool | None = None) -> bool:
    if override is not None:
        return override
    return _env_bool("FLIGHT_BG", False)


def flight_bg_level() -> float:
    # 默认略高:小喇叭听不到过弱的舱音;可用 FLIGHT_BG_LEVEL 再调
    return max(0.0, min(1.0, _env_float("FLIGHT_BG_LEVEL", 0.35)))


def radio_fx_level() -> float:
    return max(0.0, min(1.0, _env_float("RADIO_FX_LEVEL", 0.45)))


def _clamp16(x: float) -> int:
    if x > 32767:
        return 32767
    if x < -32768:
        return -32768
    return int(x)


def _iter_s16(pcm: bytes) -> Iterable[int]:
    n = len(pcm) // 2
    for i in range(n):
        yield struct.unpack_from("<h", pcm, i * 2)[0]


def _pack_s16(samples: list[int]) -> bytes:
    return b"".join(struct.pack("<h", _clamp16(s)) for s in samples)


def _one_pole_lp(x: float, y: float, alpha: float) -> float:
    return y + alpha * (x - y)


def _one_pole_hp(x: float, prev_x: float, prev_y: float, alpha: float) -> tuple[float, float]:
    y = alpha * (prev_y + x - prev_x)
    return y, x


def apply_radio_fx(pcm: bytes, sample_rate: int = 16000, *, intensity: float | None = None) -> bytes:
    """对讲机效果：带通 + 噪声/爆音 + 轻微失真与颤动。"""
    if not pcm:
        return pcm
    level = radio_fx_level() if intensity is None else max(0.0, min(1.0, intensity))
    if level <= 0.01:
        return pcm

    # 带通近似：HP ~300Hz + LP ~3400Hz
    hp_a = math.exp(-2.0 * math.pi * 300.0 / sample_rate)
    lp_a = 1.0 - math.exp(-2.0 * math.pi * 3400.0 / sample_rate)
    noise_amt = 0.04 + 0.12 * level
    drive = 1.2 + 1.8 * level
    flutter = 0.015 + 0.04 * level
    crackle_p = 0.0008 + 0.004 * level

    out: list[int] = []
    lp = 0.0
    hp_x = 0.0
    hp_y = 0.0
    rng = random.Random(0xA71C ^ len(pcm))
    for i, s in enumerate(_iter_s16(pcm)):
        x = float(s)
        # high-pass then low-pass
        hp_y, hp_x = _one_pole_hp(x, hp_x, hp_y, hp_a)
        lp = _one_pole_lp(hp_y, lp, lp_a)
        y = lp

        # soft clip / radio distortion
        y = math.tanh(y * drive / 32768.0) * 32768.0 * (0.85 + 0.1 * level)

        # hiss
        y += rng.gauss(0.0, 1.0) * 32768.0 * noise_amt

        # crackle pops
        if rng.random() < crackle_p:
            y += rng.choice((-1.0, 1.0)) * (4000 + 12000 * level) * rng.random()

        # amplitude flutter
        t = i / sample_rate
        y *= 1.0 + flutter * math.sin(2.0 * math.pi * 7.5 * t)

        # mix with dry so speech stays intelligible
        dry = float(s)
        mix = 0.35 + 0.55 * level
        out.append(_clamp16(dry * (1.0 - mix) + y * mix))
    return _pack_s16(out)


def _synth_flight_bed(n_samples: int, sample_rate: int, rng: random.Random) -> list[float]:
    """合成舱内轰鸣 + 气流噪声。

    刻意把能量放在 250~2.5kHz:Tab5 这类小喇叭几乎听不到 <150Hz 基波。
    """
    bed = [0.0] * n_samples
    # 可听频段的“引擎/通风”谐波簇
    tones = (
        (260.0, 0.22),
        (390.0, 0.16),
        (520.0, 0.12),
        (780.0, 0.08),
        (1040.0, 0.05),
    )
    for f0, amp in tones:
        phase = rng.random() * 2.0 * math.pi
        for i in range(n_samples):
            t = i / sample_rate
            bed[i] += amp * math.sin(2.0 * math.pi * f0 * t + phase)
            bed[i] += 0.35 * amp * math.sin(2.0 * math.pi * (f0 * 1.5) * t + phase * 0.7)
    # 宽带气流噪声(带通感:先 LP 再轻微 HP)
    lp = 0.0
    hp_x = 0.0
    hp_y = 0.0
    hp_a = math.exp(-2.0 * math.pi * 180.0 / sample_rate)
    for i in range(n_samples):
        n = rng.gauss(0.0, 1.0)
        lp = _one_pole_lp(n, lp, 0.18)
        hp_y, hp_x = _one_pole_hp(lp, hp_x, hp_y, hp_a)
        bed[i] += 0.38 * hp_y
        # 慢起伏,模拟座舱压力/气流变化
        bed[i] *= 0.82 + 0.18 * math.sin(2.0 * math.pi * 0.22 * i / sample_rate)
    return bed


def mix_flight_background(
    pcm: bytes,
    sample_rate: int = 16000,
    *,
    level: float | None = None,
    pad_ms: int = 320,
) -> bytes:
    """在语音前后加垫音，并在整段混入舱音。"""
    if not pcm:
        return pcm
    bg = flight_bg_level() if level is None else max(0.0, min(1.0, level))
    if bg <= 0.005:
        return pcm

    speech = list(_iter_s16(pcm))
    pad = max(0, int(sample_rate * pad_ms / 1000))
    total = pad + len(speech) + pad
    rng = random.Random(0xF11A7 ^ total)
    bed = _synth_flight_bed(total, sample_rate, rng)

    # bed 峰值归一后按 bg 放大;保证小喇叭可闻,又不过度削波
    peak = max(1e-6, max(abs(x) for x in bed))
    scale = (0.42 * bg) / peak

    out: list[int] = []
    for i in range(total):
        voice = 0.0
        if pad <= i < pad + len(speech):
            voice = float(speech[i - pad])
        # 人声下略闪避,但保留可闻舱音
        duck = 0.70 if abs(voice) > 1200 else 1.0
        y = voice * 0.92 + bed[i] * scale * duck * 32768.0
        out.append(_clamp16(y))
    return _pack_s16(out)


def process_voice_pcm(
    pcm: bytes,
    sample_rate: int = 16000,
    *,
    enable_radio_fx: bool | None = None,
    enable_flight_bg: bool | None = None,
) -> bytes:
    """按开关对 TTS PCM 做电台特效与飞行背景。"""
    if not pcm:
        return pcm
    out = pcm
    if radio_fx_enabled(enable_radio_fx):
        out = apply_radio_fx(out, sample_rate)
    if flight_bg_enabled(enable_flight_bg):
        out = mix_flight_background(out, sample_rate)
    return out
