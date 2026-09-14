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


def radio_fx_level() -> float:
    return max(0.0, min(1.0, _env_float("RADIO_FX_LEVEL", 0.45)))


def flight_bg_level() -> float:
    return max(0.0, min(1.0, _env_float("FLIGHT_BG_LEVEL", 0.10)))


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
    """合成少量舱内轰鸣 + 气流噪声（循环友好）。"""
    bed = [0.0] * n_samples
    # engine / cabin rumble harmonics
    fundamentals = (78.0, 110.0, 156.0)
    for f0 in fundamentals:
        phase = rng.random() * 2.0 * math.pi
        amp = 0.35 / len(fundamentals)
        for i in range(n_samples):
            t = i / sample_rate
            bed[i] += amp * math.sin(2.0 * math.pi * f0 * t + phase)
            bed[i] += 0.12 * amp * math.sin(2.0 * math.pi * (f0 * 2.0) * t + phase)
    # air hiss (filtered noise)
    lp = 0.0
    for i in range(n_samples):
        n = rng.gauss(0.0, 1.0)
        lp = _one_pole_lp(n, lp, 0.08)
        bed[i] += 0.22 * lp
        # slow swell
        bed[i] *= 0.85 + 0.15 * math.sin(2.0 * math.pi * 0.15 * i / sample_rate)
    return bed


def mix_flight_background(
    pcm: bytes,
    sample_rate: int = 16000,
    *,
    level: float | None = None,
    pad_ms: int = 180,
) -> bytes:
    """在语音前后加一点垫音，并在整段混入舱音。"""
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

    # normalize bed peak ~0.4 then scale by bg
    peak = max(1e-6, max(abs(x) for x in bed))
    scale = (0.35 * bg) / peak

    out: list[int] = []
    for i in range(total):
        voice = 0.0
        if pad <= i < pad + len(speech):
            voice = float(speech[i - pad])
        # duck background a bit under speech
        duck = 0.55 if abs(voice) > 800 else 1.0
        y = voice + bed[i] * scale * duck * 32768.0
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
