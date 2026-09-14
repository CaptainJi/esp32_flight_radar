"""火山引擎客户端：方舟 Chat + 豆包全双工智能对话（Duplex）TTS / 端到端。

鉴权与用户 .env 对齐：
- ARK_API_KEY + ARK_ENDPOINT_ID → 方舟 Chat Completions
- VOICE_API_KEY + VOICE_WS_URL  → openspeech duplex JSON WebSocket
"""

from __future__ import annotations

import asyncio
import audioop
import base64
import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
from websockets.asyncio.client import connect as ws_connect


class VolcError(RuntimeError):
    pass


class TtsFailed(VolcError):
    """方舟文本已生成，但 duplex TTS 失败。"""

    def __init__(self, reply_text: str, cause: Exception):
        super().__init__(f"TTS 失败: {cause}")
        self.reply_text = reply_text


@dataclass
class TurnResult:
    reply_text: str
    pcm: bytes
    sample_rate: int
    mode: str  # hybrid | duplex | ark | mock


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def mock_forced() -> bool:
    return _env("VOICE_ATC_MOCK", "0") == "1"


def has_live_credentials() -> bool:
    return bool(_env("VOICE_API_KEY") or (_env("ARK_API_KEY") and _env("ARK_ENDPOINT_ID")))


def backend_mode() -> str:
    """auto|hybrid|duplex|ark — auto 优先 hybrid（方舟+语音），否则有啥用啥。"""
    mode = _env("VOICE_BACKEND", "auto").lower() or "auto"
    if mode != "auto":
        return mode
    has_voice = bool(_env("VOICE_API_KEY"))
    has_ark = bool(_env("ARK_API_KEY") and _env("ARK_ENDPOINT_ID"))
    if has_voice and has_ark:
        return "hybrid"
    if has_voice:
        return "duplex"
    if has_ark:
        return "ark"
    return "mock"


def _voice_headers() -> dict[str, str]:
    key = _env("VOICE_API_KEY")
    if not key:
        raise VolcError("未设置 VOICE_API_KEY")
    headers = {
        "X-Api-Key": key,
        "X-Api-Connect-Id": str(uuid.uuid4()),
    }
    app_id = _env("VOICE_APP_ID")
    if app_id:
        headers["X-Api-App-Id"] = app_id
    return headers


def _ws_url() -> str:
    return _env(
        "VOICE_WS_URL",
        "wss://openspeech.bytedance.com/api/v3/duplex/realtime/dialogue",
    )


def _voice_id(lang: str = "zh") -> str:
    if (lang or "").strip().lower() in ("en", "english", "eng"):
        return _env(
            "VOICE_SPEAKER_EN",
            _env("VOICE_SPEAKER", "en_male_adam_mars_bigtts"),
        )
    return _env("VOICE_SPEAKER", "zh_male_yunzhou_jupiter_bigtts")


def _model() -> str:
    return _env("VOICE_MODEL", "1.2.6.0")


def resample_pcm_s16le(pcm: bytes, src_rate: int, dst_rate: int) -> bytes:
    if src_rate == dst_rate or not pcm:
        return pcm
    # audioop.ratecv state 跨 chunk；整段一次转换
    converted, _ = audioop.ratecv(pcm, 2, 1, src_rate, dst_rate, None)
    return converted


def trim_pcm_silence(
    pcm: bytes,
    sample_rate: int = 16000,
    *,
    frame_ms: int = 20,
    thresh: int = 180,
    pad_frames: int = 5,
) -> bytes:
    """裁掉首尾近静音。

    长录音（自动停满缓冲）常是前几秒有话、后面全静音；
    若强制保留原长 25%，静音会把 duplex ASR 拖死。最短保留用绝对时长。
    """
    if not pcm or len(pcm) < 4:
        return pcm
    frame = max(1, (sample_rate * frame_ms) // 1000) * 2  # bytes, s16le mono
    n = len(pcm) // frame
    if n < 5:
        return pcm
    levels: list[int] = []
    for i in range(n):
        chunk = pcm[i * frame : (i + 1) * frame]
        levels.append(audioop.rms(chunk, 2))
    peak = max(levels) if levels else 0
    if peak < max(120, thresh):
        return pcm
    first = next((i for i, v in enumerate(levels) if v >= thresh), None)
    if first is None:
        return pcm
    last = next((i for i in range(n - 1, -1, -1) if levels[i] >= thresh), first)
    a = max(0, first - pad_frames)
    b = min(n, last + 1 + pad_frames)
    out = pcm[a * frame : b * frame]
    min_keep = frame * 15  # ~300ms，与原长无关
    if len(out) < min_keep:
        return pcm
    return out


def _fold_asr_piece(prev: str, piece: str) -> str:
    """合并 ASR 片段：兼容增量 / 全量(累计)两种 delta。"""
    piece = (piece or "").strip()
    if not piece:
        return prev
    if not prev:
        return piece
    if piece.startswith(prev):
        return piece
    if prev.startswith(piece):
        return prev
    # 重叠后缀前缀（常见于半增量）
    max_ov = min(len(prev), len(piece), 24)
    for ov in range(max_ov, 0, -1):
        if prev.endswith(piece[:ov]):
            return prev + piece[ov:]
    return prev + piece


def normalize_asr_text(text: str) -> str:
    """压缩幻觉重复：喂喂喂喂喂… → 喂喂喂。"""
    import re

    t = (text or "").strip()
    if not t:
        return ""
    # 连续同一字符（含中文）最多保留 3 次
    t = re.sub(r"(.)\1{3,}", r"\1\1\1", t, flags=re.DOTALL)
    # 连续同一双字词：喂喂喂喂 → 喂喂
    t = re.sub(r"(.{2,}?)\1{2,}", r"\1\1", t)
    return t.strip()


def _asr_event_text(evt: dict[str, Any]) -> str:
    """优先 transcript（全量），再 delta。"""
    for key in ("transcript", "text", "delta"):
        v = evt.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _event_id() -> str:
    return uuid.uuid4().hex[:16]


async def ark_chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.7,
) -> str:
    api_key = _env("ARK_API_KEY")
    endpoint = _env("ARK_ENDPOINT_ID")
    if not api_key or not endpoint:
        raise VolcError("未设置 ARK_API_KEY / ARK_ENDPOINT_ID")
    base = _env("ARK_BASE_URL", "https://ark.cn-beijing.volces.com").rstrip("/")
    # 电台短回复不需要深度思考；开启时易拖慢甚至 ReadTimeout
    thinking = _env("ARK_THINKING", "disabled").lower() or "disabled"
    payload: dict[str, Any] = {
        "model": endpoint,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": int(_env("ARK_MAX_TOKENS", "256") or "256"),
    }
    if thinking in ("disabled", "enabled", "auto"):
        payload["thinking"] = {"type": thinking}
    timeout = httpx.Timeout(connect=15.0, read=35.0, write=30.0, pool=30.0)
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                r = await client.post(
                    f"{base}/api/v3/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                if r.status_code >= 400:
                    # 部分旧接入点不认 thinking，去掉再试一次
                    if (
                        attempt == 0
                        and "thinking" in payload
                        and r.status_code in (400, 422)
                    ):
                        payload.pop("thinking", None)
                        continue
                    raise VolcError(f"ark chat failed {r.status_code}: {r.text[:400]}")
                data = r.json()
                try:
                    content = str(data["choices"][0]["message"]["content"]).strip()
                    if content:
                        return content
                    # 偶发 content 空、只有 reasoning_content
                    reason = str(
                        data["choices"][0]["message"].get("reasoning_content") or ""
                    ).strip()
                    if reason:
                        return reason[-400:]
                    raise VolcError(f"ark chat empty content: {data!r}"[:500])
                except (KeyError, IndexError, TypeError) as e:
                    raise VolcError(f"ark chat parse error: {data!r}"[:500]) from e
        except httpx.TimeoutException as e:
            last_err = e
            await asyncio.sleep(0.4 * (attempt + 1))
            continue
        except httpx.HTTPError as e:
            last_err = e
            await asyncio.sleep(0.4 * (attempt + 1))
            continue
    raise VolcError(f"方舟对话超时/失败，请再发一次（{type(last_err).__name__}）")


# 全双工 WS 串行化，避免连续请求把火山会话打挂
_duplex_lock = asyncio.Lock()


async def _recv_json(ws: Any, timeout: float) -> dict[str, Any]:
    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    return json.loads(raw)


async def _duplex_session(instructions: str, *, lang: str = "zh"):
    """打开 duplex 会话，yield (ws, session_id)。调用方须持有 _duplex_lock。"""
    url = _ws_url()
    headers = _voice_headers()
    voice = _voice_id(lang)
    create = {
        "type": "session.create",
        "event_id": _event_id(),
        "session": {
            "model": _model(),
            "instructions": (instructions or "")[:4000],
            "audio": {
                "input": {"format": {"type": "pcm", "rate": 16000}},
                "output": {
                    "format": {"type": "pcm_s16le", "rate": 24000},
                    "voice": voice,
                },
            },
        },
    }
    async with ws_connect(
        url,
        additional_headers=headers,
        open_timeout=20,
        close_timeout=5,
        ping_interval=20,
        ping_timeout=20,
        max_size=8 * 1024 * 1024,
    ) as ws:
        await ws.send(json.dumps(create, ensure_ascii=False))
        session_id = ""
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                evt = await _recv_json(ws, timeout=15)
            except TimeoutError as e:
                raise VolcError("duplex 等待 session.created 超时") from e
            et = evt.get("type")
            if et == "error":
                err = evt.get("error") or evt
                raise VolcError(f"duplex session error: {err}")
            if et == "session.created":
                session_id = ((evt.get("session") or {}).get("id")) or ""
                break
            if et == "session.updated":
                continue
        else:
            raise VolcError("duplex 等待 session.created 超时")
        try:
            yield ws, session_id
        finally:
            try:
                await asyncio.wait_for(
                    ws.send(json.dumps({"type": "session.close", "event_id": _event_id()})),
                    timeout=2,
                )
            except Exception:
                pass


async def duplex_tts(
    text: str, *, instructions: str = "", lang: str = "zh"
) -> tuple[bytes, int]:
    """用 duplex speech_text_buffer.commit 合成 PCM（默认 24 kHz）。"""
    if not text.strip():
        return b"", 24000
    # TTS 不需要机组长 system prompt，过长易拖慢/超时
    if (lang or "").strip().lower() in ("en", "english", "eng"):
        tts_instructions = (
            "You are an airborne radio voice synthesizer. "
            "Read the given text clearly in English only; no extra commentary."
        )
    else:
        tts_instructions = "你是机载电台语音合成器，只清晰朗读给定文本，不要额外解释。"
    if instructions:
        tts_instructions = instructions[:200] + "\n" + tts_instructions

    async def _run() -> tuple[bytes, int]:
        pcm_parts: list[bytes] = []
        out_rate = 24000
        async with _duplex_lock:
            async for ws, _sid in _duplex_session(tts_instructions, lang=lang):
                await ws.send(
                    json.dumps(
                        {
                            "type": "speech_text_buffer.commit",
                            "event_id": _event_id(),
                            "text": text[:2000],
                        },
                        ensure_ascii=False,
                    )
                )
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    try:
                        evt = await _recv_json(ws, timeout=min(20.0, remaining))
                    except TimeoutError:
                        # 单次空窗不退出，继续等到总截止（避免偶发空音频）
                        if pcm_parts:
                            break
                        continue
                    et = evt.get("type")
                    if et == "error":
                        raise VolcError(f"duplex tts error: {evt.get('error') or evt}")
                    if et == "response.output_audio.delta":
                        delta = evt.get("delta") or ""
                        if delta:
                            pcm_parts.append(base64.b64decode(delta))
                    if et in (
                        "response.output_audio.done",
                        "response.done",
                        "session.closed",
                    ):
                        break
                break
        return b"".join(pcm_parts), out_rate

    try:
        return await asyncio.wait_for(_run(), timeout=55)
    except TimeoutError as e:
        raise VolcError("语音合成超时，请再发一次") from e


async def duplex_chat_turn(
    *,
    instructions: str,
    user_text: str,
    history: list[dict[str, str]],
    want_audio: bool = True,
    lang: str = "zh",
) -> tuple[str, bytes, int]:
    """端到端 duplex：写入上下文 + 用户文本，收 reply + PCM。"""
    reply_parts: list[str] = []
    reply_final = ""
    pcm_parts: list[bytes] = []
    out_rate = 24000

    async def _run() -> None:
        nonlocal reply_final
        async with _duplex_lock:
            async for ws, _sid in _duplex_session(instructions, lang=lang):
                items: list[dict[str, Any]] = []
                for m in history[-8:]:
                    role = m.get("role")
                    content = (m.get("content") or "").strip()
                    if role not in ("user", "assistant") or not content:
                        continue
                    ctype = "input_text" if role == "user" else "text"
                    items.append(
                        {
                            "type": "message",
                            "role": role,
                            "content": [{"type": ctype, "text": content}],
                        }
                    )
                if items:
                    await ws.send(
                        json.dumps(
                            {
                                "type": "conversation.item.create",
                                "event_id": _event_id(),
                                "items": items,
                            },
                            ensure_ascii=False,
                        )
                    )
                    try:
                        ack = await _recv_json(ws, timeout=5)
                        if ack.get("type") == "error":
                            raise VolcError(
                                f"duplex history error: {ack.get('error') or ack}"
                            )
                    except TimeoutError:
                        pass

                await ws.send(
                    json.dumps(
                        {
                            "type": "conversation.item.create",
                            "event_id": _event_id(),
                            "items": [
                                {
                                    "type": "message",
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "input_text",
                                            "text": user_text.strip(),
                                        }
                                    ],
                                }
                            ],
                        },
                        ensure_ascii=False,
                    )
                )

                deadline = time.monotonic() + 60
                got_useful = False
                while time.monotonic() < deadline:
                    try:
                        evt = await _recv_json(ws, timeout=25)
                    except TimeoutError:
                        break
                    et = evt.get("type")
                    if et == "error":
                        raise VolcError(f"duplex chat error: {evt.get('error') or evt}")
                    if et == "response.output_text.delta":
                        d = evt.get("delta") or ""
                        if d:
                            reply_parts.append(d)
                            got_useful = True
                    elif et == "response.output_text.done":
                        t = (evt.get("text") or "").strip()
                        if t:
                            reply_final = t
                            got_useful = True
                    elif et == "response.output_audio.delta" and want_audio:
                        delta = evt.get("delta") or ""
                        if delta:
                            pcm_parts.append(base64.b64decode(delta))
                            got_useful = True
                    elif et in ("response.output_audio.done", "response.done"):
                        if got_useful:
                            break
                    elif et == "session.closed":
                        break
                break

    try:
        await asyncio.wait_for(_run(), timeout=75)
    except TimeoutError as e:
        raise VolcError("智能对话超时，请再发一次") from e

    text = reply_final or "".join(reply_parts).strip()
    pcm = b"".join(pcm_parts)
    if not text and not pcm:
        raise VolcError(
            "duplex 未返回文本/音频（文本回合可能需改用 hybrid=方舟+TTS）。"
        )
    return text, pcm, out_rate


async def duplex_audio_turn(
    pcm: bytes,
    *,
    instructions: str,
    history: list[dict[str, str]],
    lang: str = "zh",
    sample_rate: int = 16000,
    want_audio: bool = True,
) -> tuple[str, str, bytes, int]:
    """全双工：上传用户 PCM → 转写 + 机组回复文本 + TTS PCM。

    返回 (user_transcript, reply_text, pcm_out, out_rate)。
    """
    if sample_rate != 16000:
        pcm = resample_pcm_s16le(pcm, sample_rate, 16000)
    pcm = trim_pcm_silence(pcm, 16000)
    if len(pcm) < 320:
        raise VolcError("录音太短或几乎无声")
    chunk = 3200

    async def _run() -> tuple[str, str, bytes, int]:
        transcript = ""
        live = ""
        reply_parts: list[str] = []
        reply_final = ""
        pcm_parts: list[bytes] = []
        out_rate = 24000

        async with _duplex_lock:
            async for ws, _sid in _duplex_session(instructions, lang=lang):
                items: list[dict[str, Any]] = []
                for m in history[-8:]:
                    role = m.get("role")
                    content = (m.get("content") or "").strip()
                    if role not in ("user", "assistant") or not content:
                        continue
                    ctype = "input_text" if role == "user" else "text"
                    items.append(
                        {
                            "type": "message",
                            "role": role,
                            "content": [{"type": ctype, "text": content}],
                        }
                    )
                if items:
                    await ws.send(
                        json.dumps(
                            {
                                "type": "conversation.item.create",
                                "event_id": _event_id(),
                                "items": items,
                            },
                            ensure_ascii=False,
                        )
                    )
                    try:
                        ack = await _recv_json(ws, timeout=5)
                        if ack.get("type") == "error":
                            raise VolcError(
                                f"duplex history error: {ack.get('error') or ack}"
                            )
                    except TimeoutError:
                        pass

                for i in range(0, len(pcm), chunk):
                    await ws.send(
                        json.dumps(
                            {
                                "type": "input_audio_buffer.append",
                                "event_id": _event_id(),
                                "audio": base64.b64encode(pcm[i : i + chunk]).decode(
                                    "ascii"
                                ),
                            },
                            ensure_ascii=False,
                        )
                    )
                await ws.send(
                    json.dumps(
                        {
                            "type": "input_audio_buffer.commit",
                            "event_id": _event_id(),
                        },
                        ensure_ascii=False,
                    )
                )

                # 转写常很快；端到端回复经常卡住，转写后最多再等 reply_wait。
                deadline = time.monotonic() + 40
                reply_wait = 12.0
                reply_deadline: float | None = None
                got_reply = False
                while time.monotonic() < deadline:
                    if reply_deadline is not None and time.monotonic() >= reply_deadline:
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    try:
                        evt = await _recv_json(ws, timeout=min(8.0, remaining))
                    except TimeoutError:
                        if got_reply or pcm_parts:
                            break
                        if reply_deadline is not None:
                            break
                        continue
                    et = evt.get("type")
                    if et == "error":
                        raise VolcError(f"duplex voice error: {evt.get('error') or evt}")
                    if et in (
                        "conversation.item.input_audio_transcription.delta",
                        "conversation.item.input_audio_transcription.started",
                    ):
                        piece = _asr_event_text(evt)
                        if piece:
                            if isinstance(evt.get("transcript"), str) and evt[
                                "transcript"
                            ].strip():
                                live = evt["transcript"].strip()
                            else:
                                live = _fold_asr_piece(live, piece)
                    elif et == "conversation.item.input_audio_transcription.completed":
                        transcript = _asr_event_text(evt) or live
                        if not got_reply and reply_deadline is None:
                            reply_deadline = time.monotonic() + reply_wait
                    elif et == "conversation.item.input_audio_transcription.failed":
                        raise VolcError(f"duplex asr failed: {evt}")
                    elif et == "response.output_text.delta":
                        d = evt.get("delta") or ""
                        if d:
                            reply_parts.append(d)
                            got_reply = True
                    elif et == "response.output_text.done":
                        t = (evt.get("text") or "").strip()
                        if t:
                            reply_final = t
                            got_reply = True
                    elif et == "response.output_audio.delta" and want_audio:
                        delta = evt.get("delta") or ""
                        if delta:
                            pcm_parts.append(base64.b64decode(delta))
                            got_reply = True
                    elif et in ("response.output_audio.done", "response.done"):
                        if got_reply or transcript or live:
                            break
                    elif et == "session.closed":
                        break
                break

        user_text = normalize_asr_text(transcript or live)
        reply = reply_final or "".join(reply_parts).strip()
        out = b"".join(pcm_parts)
        if not user_text and not reply and not out:
            raise VolcError("duplex 语音对讲无结果（可能太短/无语音）")
        return user_text, reply, out, out_rate

    try:
        return await asyncio.wait_for(_run(), timeout=50)
    except TimeoutError as e:
        raise VolcError("语音对讲超时，请再录一次") from e


async def duplex_asr(
    pcm: bytes,
    *,
    lang: str = "zh",
    sample_rate: int = 16000,
) -> str:
    """经全双工 duplex：上传 PCM → 取转写后 cancel 对话回复。"""
    if sample_rate != 16000:
        pcm = resample_pcm_s16le(pcm, sample_rate, 16000)
    pcm = trim_pcm_silence(pcm, 16000)
    if len(pcm) < 320:
        raise VolcError("录音太短或几乎无声")
    if (lang or "").strip().lower() in ("en", "english", "eng"):
        instructions = (
            "You are a radio speech-to-text engine. "
            "Transcribe exactly what was spoken, including short words like hello/hey/radio check. "
            "Do not invent extra words beyond the audio. Do not reply or chat."
        )
    else:
        instructions = (
            "你是机载电台语音转写引擎，只把音频里真实说过的话原样转成文字，"
            "包括很短的呼叫（例如「喂」「收到」「电台检查」）。"
            "不要凭空加长或重复；不要回答或闲聊。"
        )
    chunk = 3200

    async def _run() -> str:
        import logging

        log = logging.getLogger("voice_atc")
        transcript = ""
        live = ""
        seen: list[str] = []
        async with _duplex_lock:
            async for ws, _sid in _duplex_session(instructions, lang=lang):
                for i in range(0, len(pcm), chunk):
                    await ws.send(
                        json.dumps(
                            {
                                "type": "input_audio_buffer.append",
                                "event_id": _event_id(),
                                "audio": base64.b64encode(pcm[i : i + chunk]).decode(
                                    "ascii"
                                ),
                            },
                            ensure_ascii=False,
                        )
                    )
                await ws.send(
                    json.dumps(
                        {
                            "type": "input_audio_buffer.commit",
                            "event_id": _event_id(),
                        },
                        ensure_ascii=False,
                    )
                )
                deadline = time.monotonic() + 35
                while time.monotonic() < deadline:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    try:
                        evt = await _recv_json(ws, timeout=min(12.0, remaining))
                    except TimeoutError:
                        if transcript or live:
                            break
                        continue
                    et = str(evt.get("type") or "")
                    if et:
                        seen.append(et)
                    if et == "error":
                        raise VolcError(f"duplex asr error: {evt.get('error') or evt}")
                    if et in (
                        "conversation.item.input_audio_transcription.delta",
                        "conversation.item.input_audio_transcription.started",
                    ):
                        piece = _asr_event_text(evt)
                        if piece:
                            # transcript 字段多为全量；仅有 delta 时用智能合并
                            if isinstance(evt.get("transcript"), str) and evt[
                                "transcript"
                            ].strip():
                                live = evt["transcript"].strip()
                            else:
                                live = _fold_asr_piece(live, piece)
                    elif et == "conversation.item.input_audio_transcription.completed":
                        transcript = _asr_event_text(evt) or live
                        try:
                            await ws.send(
                                json.dumps(
                                    {
                                        "type": "response.cancel",
                                        "event_id": _event_id(),
                                    },
                                    ensure_ascii=False,
                                )
                            )
                        except Exception:
                            pass
                        break
                    elif et == "conversation.item.input_audio_transcription.failed":
                        raise VolcError(f"duplex asr failed: {evt}")
                    elif et in (
                        "response.output_text.delta",
                        "response.output_audio.delta",
                        "response.done",
                    ):
                        if transcript or live:
                            try:
                                await ws.send(
                                    json.dumps(
                                        {
                                            "type": "response.cancel",
                                            "event_id": _event_id(),
                                        },
                                        ensure_ascii=False,
                                    )
                                )
                            except Exception:
                                pass
                            break
                    elif et == "session.closed":
                        break
                break
        raw = (transcript or live).strip()
        text = normalize_asr_text(raw)
        if raw != text:
            log.info("asr normalize %r -> %r", raw[:80], text[:80])
        if not text:
            tail = ",".join(seen[-8:]) if seen else "(no events)"
            raise VolcError(f"duplex ASR 未返回文本（可能太短/无语音） events={tail}")
        return text

    try:
        return await asyncio.wait_for(_run(), timeout=45)
    except TimeoutError as e:
        raise VolcError("语音识别超时，请再录一次") from e


async def radio_turn(
    *,
    system_prompt: str,
    user_text: str,
    history: list[dict[str, str]],
    want_audio: bool = True,
    target_sample_rate: int = 16000,
    lang: str = "zh",
) -> TurnResult:
    """执行一轮无线电对讲，统一输出 target_sample_rate 的 PCM。"""
    if mock_forced() or not has_live_credentials():
        raise VolcError("MOCK")  # 由 main 处理假回复

    mode = backend_mode()
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for m in history[-8:]:
        if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip():
            messages.append(
                {"role": m["role"], "content": m["content"].strip()}
            )
    messages.append({"role": "user", "content": user_text.strip()})

    if mode == "duplex":
        text, pcm, rate = await duplex_chat_turn(
            instructions=system_prompt,
            user_text=user_text,
            history=history,
            want_audio=want_audio,
            lang=lang,
        )
        if want_audio and pcm:
            pcm = resample_pcm_s16le(pcm, rate, target_sample_rate)
        else:
            pcm = b""
        return TurnResult(text or "(empty)", pcm, target_sample_rate, "duplex")

    if mode == "ark":
        text = await ark_chat(messages)
        return TurnResult(text, b"", target_sample_rate, "ark")

    # hybrid（默认）：方舟生成机组文本，duplex 只做 TTS
    text = await ark_chat(messages)
    pcm = b""
    if want_audio and text:
        try:
            raw, rate = await duplex_tts(text, lang=lang)
            pcm = resample_pcm_s16le(raw, rate, target_sample_rate)
            if not pcm:
                raise VolcError("duplex TTS 返回空音频")
        except VolcError as e:
            raise TtsFailed(text, e) from e
    return TurnResult(text, pcm, target_sample_rate, "hybrid")


async def asr_pcm(
    pcm: bytes,
    *,
    lang: str = "zh",
    sample_rate: int = 16000,
) -> tuple[str, bool]:
    """短语音识别。返回 (text, mock)。有 VOICE_API_KEY 时走 duplex 真实转写。"""
    import logging

    from prompt import normalize_lang

    lang = normalize_lang(lang)
    if not pcm or len(pcm) < 320:  # <10ms @16k s16
        raise VolcError("录音太短")

    if mock_forced() or not _env("VOICE_API_KEY"):
        if lang == "en":
            return "ASR mock: Radio check, please acknowledge.", True
        return "ASR mock: 电台检查，请回答。", True

    # 诊断板端麦电平（偏低时上游常只回 committed、不给转写）
    try:
        peak = audioop.max(pcm, 2)
        rms = audioop.rms(pcm, 2)
        logging.getLogger("voice_atc").info(
            "asr pcm=%u peak=%d rms=%d lang=%s", len(pcm), peak, rms, lang
        )
    except Exception:
        pass

    text = await duplex_asr(pcm, lang=lang, sample_rate=sample_rate)
    return text, False
