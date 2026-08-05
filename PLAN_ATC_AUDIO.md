# ATC 語音串流(擱置中,可隨時恢復)

在 ESP32-P4 板上透過既有的 ES8311 codec 播放 ATC 語音。

**狀態:可行性已完整驗證,尚未動工。** 缺的只有一個資料點(見「唯一缺的一塊」)。
驗證日期 2026-08-05。

## 為什麼是串流而不是 SDR

先前評估過在 P4 上接 SDR 同時收 ADS-B 與航空頻段,結論是不可行:

- ADS-B 在 1090 MHz、航空頻段在 118–137 MHz,相差約 950 MHz,**一支 dongle 不可能同時收**,要兩支。
- RTL-SDR @ 2.4 MSPS = 4.8 MB/s I/Q。dump1090 在 700 MHz 的樹莓派一代上就吃掉大半顆核心;P4 是雙核 RISC-V **360 MHz**、無專用 DSP 加速器。
- 更致命的是 PSRAM 頻寬:光是面板掃描 DMA 就 1024×600×2×60 ≈ **73 MB/s**,而掃描線的流暢度本來就被這個壓著。再塞兩路 I/Q 串流進出 PSRAM,UI 必崩。
- P4 上還沒有 USB host + RTL-SDR 驅動(`usb_host` 只在 p1ngb4ck 的 fork,RTL-SDR 驅動根本不存在)。

**只做音訊**的話 CPU 負擔會大幅下降(AM 解調 12 kHz 頻道很便宜),但仍需自己寫 USB
host + 驅動。若哪天真要走本地射頻,**專用航空頻段接收模組**比 SDR 實際得多 ——
注意常被推薦的 **Si4735/Si4732 並不涵蓋 118–137 MHz**(它們是 FM 64–108 MHz +
AM/短波);能收航空頻段的是 TEF6686 這類模組配玩家韌體,或傳統類比接收機套件。

## 已驗證的事實(全部實測,非推論)

**1. Cloudflare 只擋網頁,不擋串流。**

```
https://www.liveatc.net/play/rctp_twr.pls   → 403   (Cloudflare)
http://d.liveatc.net/<mount>                → 302   (分派器,沒被擋)
```

**2. 串流節點可直接以純 HTTP 取用 —— 不需要 TLS、不需要處理轉址。**

```
$ curl -D - http://s1-fmt2.liveatc.net/kjfk_twr
HTTP/1.1 200 OK
content-type: audio/mpeg
icy-name: KJFK Tower 119.1
```

這點對本專案特別重要:專案歷史上吃過 TLS 記憶體不足的苦頭
(`Dynamic Impl: alloc() failed` → `esp-aes: Failed to allocate memory`),純 HTTP
完全繞開那個雷。

走 `d.liveatc.net` 的話最後一跳是 HTTPS/HTTP2,會把 TLS 加回來。

**3. 對照組確認方法本身可行。** `kjfk_twr`、`klax_twr` 都收得到連續 MP3
(curl 抓到 21 KB / 40 KB 才被上限中斷);`kbos_twr` 回 404(該 feed 不存在或離線)。

**4. 播放端完全現成。** ESPHome 2026.6.5 有
`esphome/components/speaker/media_player/`(`speaker_media_player` + `audio_pipeline`),
`audio` 元件有 MP3 解碼(`request_mp3_support()`)。**不需要寫任何 DSP。**

**5. P4 硬體已經就緒且在用。** ES8311 codec、I2S(MCLK 13 / BCLK 12 / LRCLK 10 /
DOUT 9)、GPIO53 功放致能 —— 鬧鈴的 rtttl 已經在用這條路。

## 唯一缺的一塊

**台灣 feed 的掛載名稱。** 猜過並全部 404:`rctp_twr`、`rctp_app`、`rctp_gnd`、
`rctp`、`rcss_twr`、`rcss_app`、`rctp1`、`rctp2`。

恢復這件事的第一步:用瀏覽器(能過 Cloudflare)取得確切網址 ——

```
https://www.liveatc.net/play/<mount>.pls      ← 小文字檔,取其中的 File1= 那行
```

或在 https://www.liveatc.net/search/?icao=rctp 頁面按播放,從瀏覽器開發者工具的
Network 分頁複製音訊請求的網址。

拿到之後先用 curl 驗一次(串流主機沒有 Cloudflare,本機就能測):

```bash
curl -sS -D - -o /dev/null --max-filesize 4000 \
  -A "Mozilla/5.0" http://s1-fmt2.liveatc.net/<mount>
# 期待:HTTP/1.1 200 + content-type: audio/mpeg + icy-name
```

## 動工時要做的事

1. `media_player: platform: speaker`,指向既有的 `local_spk`,`audio_pipeline` 開 MP3。
2. **喇叭仲裁**(必須先決定):`local_spk` 目前被鬧鈴的 rtttl 佔用,同一顆喇叭不能
   同時播兩路。建議「鬧鈴響時暫停 ATC、鈴聲結束後恢復」而不是單純蓋過去。
3. **功放致能**:GPIO53 目前是 `restore_mode: ALWAYS_OFF`、只在響鈴時上電(避免底噪)。
   ATC 播放期間要一起管理它的開關。
4. **UI**:開關放哪(鬧鐘頁?設定頁?)、要不要音量控制、要不要選頻道。
5. **節點寫死的脆弱性**:`s1-fmt2` 是分派器當下挑的節點,LiveATC 可能換。建議先試
   寫死的節點,失敗再退回 `d.liveatc.net`(要 TLS + 轉址)。
6. 取樣率:`local_spk` 目前設 16 kHz 單聲道(配合 rtttl,見 ESPHome rtttl.cpp 的
   SAMPLE_RATE);LiveATC 的 MP3 通常是 11.025 或 22.05 kHz,交給 media_player 重取樣。

## 需要你自己判斷的一點

LiveATC 的服務條款禁止自動化存取與轉播。個人裝置收聽在實務上與瀏覽器無異,但這是
使用者的決定,不是技術問題。
