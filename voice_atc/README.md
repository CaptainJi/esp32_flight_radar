# Voice ATC 中继（小智式：板端采播，云端 ASR/LLM/TTS）

当前仓库的 ESPHome 雷达固件**不直接**跑小智客户端；本目录提供同构中继，
先用文本对讲验证「选机上下文 → 机组角色 LLM → TTS」，再接到雷达 CALL 按钮。

## 能力

| 阶段 | 状态 |
|------|------|
| `POST /v1/radio/turn` 文本对讲 + 航班上下文 | ✅ |
| MiniMax Chat + TTS（PCM 16 kHz） | ✅ |
| 浏览器联调页 `/` | ✅ |
| 无 Key 时 MOCK 回复 | ✅ |
| ASR / 小智 WebSocket 协议 | ⏳ 下一阶段 |
| 雷达固件 CALL 面板 | ⏳ 同分支进行中 |

## 快速启动

```bash
cd voice_atc
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env：填入 MINIMAX_API_KEY；国内默认 api.minimaxi.com

python main.py
# 浏览器打开 http://127.0.0.1:8765/
```

不配 Key 时自动 MOCK，也可强制：`VOICE_ATC_MOCK=1`。

## API

`POST /v1/radio/turn`

```json
{
  "flight": {
    "callsign": "CPA123",
    "type": "B77W",
    "registration": "B-KPF",
    "route": "VHHH-ZBAA",
    "altitude_m": 10668,
    "speed_ms": 250,
    "track_deg": 15,
    "squawk": "6101",
    "icao24": "780A1B"
  },
  "user_text": "CPA123, say altitude.",
  "history": [],
  "want_audio": true,
  "session_id": ""
}
```

返回：`reply_text`、`audio_url`（raw PCM）、`audio_pcm_b64`、`latency_ms`。

播放 PCM 示例：

```bash
ffplay -f s16le -ar 16000 -ac 1 http://127.0.0.1:8765/v1/audio/xxxx.pcm
```

## 与小智的关系

- **可复用**：服务端分工、会话、角色 prompt、后续可换成 `xiaozhi-esp32-server`。
- **暂不复用**：完整小智固件（与 ESPHome LVGL 雷达互斥）。
- **建议路径**：本中继验证产品逻辑 → 雷达加 CALL/文本短语 → 再上麦克风/OPUS/小智协议。

## 环境变量

见 `.env.example`。国际 Key 请设：

```
MINIMAX_BASE_URL=https://api.minimax.io
```
