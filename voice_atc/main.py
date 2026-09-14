"""
语音机组中继：设备 / 网页 → 本服务 → MiniMax LLM (+ TTS)。

对齐小智架构：板端只做采播与 UI，ASR/LLM/TTS 在服务端。
当前 MVP：文本对讲 + TTS；ASR 留给下一阶段（小智协议或第三方）。
"""

from __future__ import annotations

import base64
import os
import time
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from minimax_client import MiniMaxError, chat, tts_pcm
from prompt import build_system_prompt

load_dotenv()

ROOT = Path(__file__).resolve().parent
AUDIO_DIR = ROOT / "data" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="ESP32 Flight Radar Voice ATC", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


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
    session_id: str = ""


class RadioTurnResponse(BaseModel):
    session_id: str
    reply_text: str
    audio_url: str | None = None
    audio_pcm_b64: str | None = None
    sample_rate: int = 16000
    mock: bool = False
    latency_ms: int = 0


def _mock_reply(flight: FlightContext, user_text: str) -> str:
    cs = flight.callsign or "TRAFFIC"
    fl = (flight.altitude_m or 0) * 0.032808
    return (
        f"{cs}, copy your transmission. "
        f"Simulated radio only — heard: 「{user_text[:80]}」。"
        f" Indicating about FL{fl:.0f}, standing by."
    )


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse((ROOT / "static" / "index.html").read_text(encoding="utf-8"))


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "has_key": bool(os.getenv("MINIMAX_API_KEY", "").strip()),
        "base": os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com"),
        "mock": os.getenv("VOICE_ATC_MOCK", "0") == "1"
        or not os.getenv("MINIMAX_API_KEY", "").strip(),
    }


@app.post("/v1/radio/turn", response_model=RadioTurnResponse)
async def radio_turn(req: RadioTurnRequest) -> RadioTurnResponse:
    t0 = time.perf_counter()
    sid = req.session_id or uuid.uuid4().hex[:12]
    mock = os.getenv("VOICE_ATC_MOCK", "0") == "1" or not os.getenv(
        "MINIMAX_API_KEY", ""
    ).strip()

    if mock:
        reply = _mock_reply(req.flight, req.user_text)
    else:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": build_system_prompt(req.flight.model_dump())}
        ]
        for m in req.history[-8:]:
            if m.role in ("user", "assistant") and m.content.strip():
                messages.append({"role": m.role, "content": m.content.strip()})
        messages.append({"role": "user", "content": req.user_text.strip()})
        try:
            reply = await chat(messages)
        except MiniMaxError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

    audio_url = None
    audio_b64 = None
    if req.want_audio and reply:
        try:
            if mock:
                pcm = b"\x00\x00" * 3200  # 0.2s silence @16k s16le
            else:
                pcm = await tts_pcm(reply, sample_rate=16000)
            name = f"{sid}_{int(time.time())}.pcm"
            path = AUDIO_DIR / name
            path.write_bytes(pcm)
            audio_url = f"/v1/audio/{name}"
            audio_b64 = base64.b64encode(pcm).decode("ascii")
        except MiniMaxError as e:
            reply = reply + f"\n\n[TTS 失败: {e}]"

    return RadioTurnResponse(
        session_id=sid,
        reply_text=reply,
        audio_url=audio_url,
        audio_pcm_b64=audio_b64,
        sample_rate=16000,
        mock=mock,
        latency_ms=int((time.perf_counter() - t0) * 1000),
    )


@app.get("/v1/audio/{name}")
async def get_audio(name: str) -> FileResponse:
    if "/" in name or ".." in name or not name.endswith(".pcm"):
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
    port = int(os.getenv("VOICE_ATC_PORT", "8765"))
    uvicorn.run("main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
