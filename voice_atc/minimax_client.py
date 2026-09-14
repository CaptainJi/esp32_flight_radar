"""MiniMax Chat + TTS 客户端（国内 api.minimaxi.com / 国际 api.minimax.io）。"""

from __future__ import annotations

import binascii
import os
from typing import Any

import httpx


class MiniMaxError(RuntimeError):
    pass


def _base() -> str:
    return os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com").rstrip("/")


def _key() -> str:
    k = os.getenv("MINIMAX_API_KEY", "").strip()
    if not k:
        raise MiniMaxError("未设置 MINIMAX_API_KEY")
    return k


def _headers() -> dict[str, str]:
    h = {
        "Authorization": f"Bearer {_key()}",
        "Content-Type": "application/json",
    }
    gid = os.getenv("MINIMAX_GROUP_ID", "").strip()
    if gid:
        h["GroupId"] = gid
    return h


async def chat(messages: list[dict[str, str]], *, temperature: float = 0.7) -> str:
    """OpenAI 兼容 Chat Completions；失败再试旧版 chatcompletion_v2。"""
    model = os.getenv("MINIMAX_CHAT_MODEL", "MiniMax-M2.5")
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 512,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            f"{_base()}/v1/chat/completions",
            headers=_headers(),
            json=payload,
        )
        if r.status_code >= 400:
            # 兼容部分账号仍走 v2
            r2 = await client.post(
                f"{_base()}/v1/text/chatcompletion_v2",
                headers=_headers(),
                json=payload,
            )
            if r2.status_code >= 400:
                raise MiniMaxError(
                    f"chat failed {r.status_code}: {r.text[:400]} | "
                    f"v2 {r2.status_code}: {r2.text[:400]}"
                )
            data = r2.json()
            # v2: choices[0].message.content 或 reply
            choices = data.get("choices") or []
            if choices:
                msg = choices[0].get("message") or {}
                content = msg.get("content") or choices[0].get("text") or ""
                if content:
                    return str(content).strip()
            if data.get("reply"):
                return str(data["reply"]).strip()
            raise MiniMaxError(f"chat v2 unexpected: {data!r}"[:500])
        data = r.json()
        try:
            return str(data["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError) as e:
            raise MiniMaxError(f"chat parse error: {data!r}"[:500]) from e


async def tts_pcm(text: str, *, sample_rate: int = 16000) -> bytes:
    """同步 T2A，返回 PCM（便于 ESP I2S）；失败则返回空 bytes。"""
    if not text.strip():
        return b""
    model = os.getenv("MINIMAX_TTS_MODEL", "speech-2.6-turbo")
    voice = os.getenv("MINIMAX_VOICE_ID", "male-qn-qingse")
    payload = {
        "model": model,
        "text": text[:2000],
        "stream": False,
        "voice_setting": {
            "voice_id": voice,
            "speed": 1.0,
            "vol": 1.0,
            "pitch": 0,
        },
        "audio_setting": {
            "sample_rate": sample_rate,
            "bitrate": 128000,
            "format": "pcm",
            "channel": 1,
        },
    }
    async with httpx.AsyncClient(timeout=90.0) as client:
        r = await client.post(
            f"{_base()}/v1/t2a_v2",
            headers=_headers(),
            json=payload,
        )
        if r.status_code >= 400:
            raise MiniMaxError(f"tts failed {r.status_code}: {r.text[:400]}")
        data = r.json()
        base_resp = data.get("base_resp") or {}
        if base_resp.get("status_code", 0) not in (0, None):
            raise MiniMaxError(f"tts status: {base_resp}")
        audio_hex = (data.get("data") or {}).get("audio") or ""
        if not audio_hex:
            raise MiniMaxError(f"tts no audio: {data!r}"[:500])
        return binascii.unhexlify(audio_hex)
