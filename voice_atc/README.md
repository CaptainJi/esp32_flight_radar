# Voice ATC 中继（小智式：板端采播，云端 ASR/LLM/TTS）

当前仓库的 ESPHome 雷达固件**不直接**跑语音客户端；本目录提供同构中继。
供应商：**火山引擎**（方舟 Chat + 豆包全双工智能对话 Duplex）。

默认端口：**18650**（宿主机与容器一致）。

## 能力

| 阶段 | 状态 |
|------|------|
| `POST /v1/radio/turn` 文本对讲 + 航班上下文 | ✅ |
| `lang=zh\|en` 硬锁回复/TTS 语种 | ✅ |
| 方舟 Chat（`ARK_*`） | ✅ |
| Duplex TTS / 端到端对话（`VOICE_*`） | ✅ |
| 无线电干扰 + 飞行背景音（服务端后处理） | ✅ |
| 浏览器联调页 `/`（WAV 可播） | ✅ |
| 无 Key 时 MOCK 回复 | ✅ |
| Docker / Compose | ✅ |
| 板端麦克风 `REC` | ✅ 停录后 **语音直发**（`/v1/radio/voice_turn`：默认 ASR→方舟→TTS；`VOICE_BACKEND=duplex` 可试端到端）；另保留 `/v1/radio/asr` |

## 后端模式（`VOICE_BACKEND`）

| 值 | 行为 |
|----|------|
| `auto`（默认） | 同时有方舟+语音 → `hybrid`；仅语音 → `duplex`；仅方舟 → `ark` |
| `hybrid` | 方舟生成机组文本 + Duplex `speech_text_buffer` TTS |
| `duplex` | 全双工智能对话端到端（文本写入 conversation） |
| `ark` | 仅方舟文本，无 TTS |

## Docker（推荐）

```bash
cd voice_atc
cp .env.example .env
# 编辑 .env：填 ARK_API_KEY、ARK_ENDPOINT_ID、VOICE_API_KEY

docker compose up -d --build
# 镜像标签: esp32-flight-radar/voice-atc:18650

curl -s http://127.0.0.1:18650/health
# 浏览器: http://127.0.0.1:18650/
# Tab5 Voice ATC URL（须填电脑局域网 IP，不是 127.0.0.1）:
#   http://192.168.12.59:18650
# 若板端 voice http -1 / connection abort：
#   1) 设备 NETWORK 页 ATC 改成上面地址并 SAVE（NVS 会记住旧值）
#   2) 手机浏览器打开同一 URL 的 /health，确认局域网能通
#   3) 管理员运行 open_firewall_18650.ps1 放行入站 TCP 18650
#   4) Docker Desktop 对局域网设备常不通：改用本机直跑（见下）
```

### Windows 本机直跑（Tab5 连不通 Docker 时用）

管理员先跑一次 `open_firewall_18650.ps1`，再：

```powershell
cd D:\WSL\home\esp32_flight_radar\voice_atc
.\run_windows.ps1
```

会监听 `0.0.0.0:18650`。Tab5 ATC 填 `http://192.168.12.59:18650`。

仅构建镜像：

```bash
docker build -t esp32-flight-radar/voice-atc:18650 .
```

导出给其它机器：

```bash
docker save esp32-flight-radar/voice-atc:18650 | gzip > voice-atc-18650.tar.gz
gunzip -c voice-atc-18650.tar.gz | docker load
docker run -d --name voice-atc -p 18650:18650 --env-file .env \
  -v voice_atc_data:/app/data esp32-flight-radar/voice-atc:18650
```

## 本地 Python 启动

```bash
cd voice_atc
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py
```

强制 MOCK：`VOICE_ATC_MOCK=1`。

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
  "want_pcm_b64": false,
  "session_id": "",
  "lang": "zh"
}
```

返回：`reply_text`、`audio_url`（PCM 16 kHz）、`audio_wav_url`、`backend`、`radio_fx`、`flight_bg`、`lang`、`latency_ms`。

可选请求字段：`radio_fx` / `flight_bg`（bool，覆盖服务端默认开关）；`lang`=`zh`|`en`（硬锁回复与 TTS 语种，默认 `zh`）。

`POST /v1/radio/voice_turn`

Body：`application/octet-stream` raw PCM s16le mono。头 `X-Voice-Meta`：航班上下文 / history / lang / fx JSON。返回同 `RadioTurnResponse`（含 `user_text` 转写、`reply_text`、`audio_url`）。板端自由对话 **REC 停录后走此接口直发**，不再先 ASR 填框。

`POST /v1/radio/asr?lang=zh&sr=16000`

Body：`application/octet-stream` raw PCM。返回 `{ ok, text, lang, mock, ... }`（仅转写）。有 Key 时 duplex 真实转写；无 Key / `VOICE_ATC_MOCK=1` 时 MOCK。

## 音频特效开关

| 变量 | 默认 | 说明 |
|------|------|------|
| `RADIO_FX` | `0` | 无线电干扰（带通/噪声/爆音）；板端 CALL「干扰」可覆盖 |
| `RADIO_FX_LEVEL` | `0.45` | 干扰强度 0~1 |
| `FLIGHT_BG` | `0` | 舱内轰鸣背景；板端 CALL「背景」可覆盖 |
| `FLIGHT_BG_LEVEL` | `0.35` | 背景音量 0~1（过低在小喇叭上几乎听不见） |

联调页也有勾选框，会按次覆盖环境变量。

## 环境变量

见 `.env.example`。电台短句请保持 `ARK_THINKING=disabled`，否则方舟深度思考容易导致后续回合 `ReadTimeout`。

不要把 `.env` / Key 提交进 git。
