"""
语音机组中继：设备 / 网页 → 本服务 → 火山方舟 + 豆包全双工智能对话。

对齐小智架构：板端只做采播与 UI，ASR/LLM/TTS 在服务端。
当前 MVP：文本对讲 + TTS（默认 hybrid：方舟对话 + duplex TTS）。
"""

from __future__ import annotations

import asyncio
import base64
import math
import os
import struct
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from prompt import build_system_prompt
from radio_fx import (
    flight_bg_enabled,
    flight_bg_level,
    process_voice_pcm,
    radio_fx_enabled,
    radio_fx_level,
)
from volc_client import (
    TtsFailed,
    VolcError,
    has_live_credentials,
    mock_forced,
    radio_turn,
)

load_dotenv()

ROOT = Path(__file__).resolve().parent
AUDIO_DIR = ROOT / "data" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
TARGET_SR = 16000


def pcm_s16le_to_wav(pcm: bytes, sample_rate: int = 16000, channels: int = 1) -> bytes:
    """把 raw PCM s16le 包成浏览器可播的 WAV。"""
    bits = 16
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(pcm),
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits,
        b"data",
        len(pcm),
    )
    return header + pcm


def _mock_tone_pcm(duration_s: float = 0.5, sample_rate: int = 16000, freq: float = 880.0) -> bytes:
    """MOCK 可听见的短提示音（非静音），方便联调播放链路。"""
    n = int(duration_s * sample_rate)
    out = bytearray(n * 2)
    for i in range(n):
        t = i / sample_rate
        env = min(1.0, t * 25.0) * max(0.15, 1.0 - t / duration_s)
        sample = int(14000 * env * math.sin(2 * math.pi * freq * t))
        struct.pack_into("<h", out, i * 2, max(-32767, min(32767, sample)))
    return bytes(out)


app = FastAPI(title="ESP32 Flight Radar Voice ATC", version="0.3.0")
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


def _err_payload(status: int, detail: Any) -> dict[str, Any]:
    if isinstance(detail, list):
        msg = "; ".join(
            f"{'.'.join(str(x) for x in (e.get('loc') or []))}: {e.get('msg')}"
            if isinstance(e, dict)
            else str(e)
            for e in detail
        )
    else:
        msg = str(detail)
    return {"ok": False, "detail": msg, "error": msg}


@app.exception_handler(HTTPException)
async def http_exception_handler(_req: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content=_err_payload(exc.status_code, exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_req: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content=_err_payload(422, exc.errors()))


@app.exception_handler(Exception)
async def unhandled_exception_handler(_req: Request, exc: Exception):
    # 避免返回纯文本 "Internal Server Error" 导致前端 JSON.parse 崩
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content=_err_payload(500, f"{type(exc).__name__}: {exc}"),
    )


class FlightContext(BaseModel):
    callsign: str = ""
    type: str = ""
    registration: str = ""
    icao24: str = ""
    route: str = ""
    altitude_m: float | None = None
    speed_ms: float | None = None
    track_deg: float | None = None
    vs_ms: float | None = None
    squawk: str = ""
    operator: str = ""
    radio_call: str = ""
    description: str = ""


class ChatMessage(BaseModel):
    role: str
    content: str


class RadioTurnRequest(BaseModel):
    flight: FlightContext = Field(default_factory=FlightContext)
    user_text: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list)
    want_audio: bool = True
    # 默认不返回 base64:板端 ArduinoJson 扛不住 ~180KB JSON;浏览器用 audio_wav_url 即可
    want_pcm_b64: bool = False
    session_id: str = ""
    # None = 跟随服务端环境变量开关
    radio_fx: bool | None = None
    flight_bg: bool | None = None


class RadioTurnResponse(BaseModel):
    session_id: str
    reply_text: str
    audio_url: str | None = None
    audio_wav_url: str | None = None
    audio_pcm_b64: str | None = None
    sample_rate: int = 16000
    mock: bool = False
    backend: str = "mock"
    radio_fx: bool = False
    flight_bg: bool = False
    latency_ms: int = 0


def _mock_reply(flight: FlightContext, user_text: str) -> str:
    cs = flight.callsign or "TRAFFIC"
    fl = (flight.altitude_m or 0) * 0.032808
    return (
        f"{cs}, copy your transmission. "
        f"Simulated radio only — heard: 「{user_text[:80]}」。"
        f" Indicating about FL{fl:.0f}, standing by."
    )


def _is_mock() -> bool:
    return mock_forced() or not has_live_credentials()


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse((ROOT / "static" / "index.html").read_text(encoding="utf-8"))


@app.get("/health")
async def health() -> dict[str, Any]:
    from volc_client import backend_mode

    mode = backend_mode() if has_live_credentials() and not mock_forced() else "mock"
    return {
        "ok": True,
        "provider": "volcengine",
        "has_key": has_live_credentials(),
        "has_ark": bool(os.getenv("ARK_API_KEY", "").strip()),
        "has_voice": bool(os.getenv("VOICE_API_KEY", "").strip()),
        "ws": os.getenv(
            "VOICE_WS_URL",
            "wss://openspeech.bytedance.com/api/v3/duplex/realtime/dialogue",
        ),
        "backend": mode,
        "mock": _is_mock(),
        "radio_fx": radio_fx_enabled(),
        "radio_fx_level": radio_fx_level(),
        "flight_bg": flight_bg_enabled(),
        "flight_bg_level": flight_bg_level(),
    }


@app.post("/v1/radio/turn", response_model=RadioTurnResponse)
async def radio_turn_api(req: RadioTurnRequest) -> RadioTurnResponse:
    t0 = time.perf_counter()
    sid = req.session_id or uuid.uuid4().hex[:12]
    system = build_system_prompt(req.flight.model_dump())
    history = [m.model_dump() for m in req.history]

    mock = _is_mock()
    backend = "mock"
    reply = ""
    pcm = b""
    use_fx = radio_fx_enabled(req.radio_fx)
    use_bg = flight_bg_enabled(req.flight_bg)

    if mock:
        reply = _mock_reply(req.flight, req.user_text)
        if req.want_audio:
            pcm = _mock_tone_pcm(sample_rate=TARGET_SR)
    else:
        try:
            result = await radio_turn(
                system_prompt=system,
                user_text=req.user_text.strip(),
                history=history,
                want_audio=req.want_audio,
                target_sample_rate=TARGET_SR,
            )
            reply = result.reply_text
            pcm = result.pcm
            backend = result.mode
        except TtsFailed as e:
            reply = e.reply_text + f"\n\n[{e}]"
            backend = "hybrid"
            pcm = b""
        except VolcError as e:
            msg = str(e)
            code = 504 if ("超时" in msg or "Timeout" in msg) else 502
            raise HTTPException(status_code=code, detail=msg) from e
        except TimeoutError as e:
            raise HTTPException(status_code=504, detail="上游超时，请再发一次") from e

    audio_url = None
    audio_wav_url = None
    audio_b64 = None
    if req.want_audio and pcm:
        pcm = await asyncio.to_thread(
            process_voice_pcm,
            pcm,
            TARGET_SR,
            enable_radio_fx=use_fx,
            enable_flight_bg=use_bg,
        )
        stem = f"{sid}_{int(time.time())}"
        name = f"{stem}.pcm"
        (AUDIO_DIR / name).write_bytes(pcm)
        audio_url = f"/v1/audio/{name}"
        audio_wav_url = f"/v1/audio/{stem}.wav"
        if req.want_pcm_b64:
            audio_b64 = base64.b64encode(pcm).decode("ascii")

    return RadioTurnResponse(
        session_id=sid,
        reply_text=reply,
        audio_url=audio_url,
        audio_wav_url=audio_wav_url,
        audio_pcm_b64=audio_b64,
        sample_rate=TARGET_SR,
        mock=mock,
        backend=backend,
        radio_fx=use_fx,
        flight_bg=use_bg,
        latency_ms=int((time.perf_counter() - t0) * 1000),
    )


@app.get("/v1/audio/{name}", response_model=None)
async def get_audio(name: str):
    if "/" in name or ".." in name:
        raise HTTPException(status_code=404, detail="not found")
    if name.endswith(".wav"):
        pcm_name = name[:-4] + ".pcm"
        path = AUDIO_DIR / pcm_name
        if not path.is_file():
            raise HTTPException(status_code=404, detail="not found")
        wav = pcm_s16le_to_wav(path.read_bytes(), sample_rate=TARGET_SR)
        return Response(
            content=wav,
            media_type="audio/wav",
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": f'inline; filename="{name}"',
            },
        )
    if not name.endswith(".pcm"):
        raise HTTPException(status_code=404, detail="not found")
    path = AUDIO_DIR / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=name,
        headers={"Cache-Control": "no-store"},
    )


def main() -> None:
    import uvicorn

    host = os.getenv("VOICE_ATC_HOST", "0.0.0.0")
    port = int(os.getenv("VOICE_ATC_PORT", "18650"))
    uvicorn.run("main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
