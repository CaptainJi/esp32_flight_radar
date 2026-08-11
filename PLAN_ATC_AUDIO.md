# ATC 語音串流(擱置中,可隨時恢復)

在 ESP32-P4 板上透過既有的 ES8311 codec 播放 ATC 語音。

**狀態:技術上可行且已完整驗證(2026-08-05),但擱置的原因在 2026-08-10 改變了 ——
現在卡住的不是技術,是授權。** 見文末「真正的阻擋:LiveATC 服務條款」。

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

> **注意:第 1、2 點已於 2026-08-10 部分失效**(分派器現在被擋)。
> 讀完本節請接著看下方「2026-08-10 更正:分派器已被 Cloudflare 擋」。

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

## ~~唯一缺的一塊~~ (2026-08-10 更正:這一節的前提是錯的)

原本寫「台灣 feed 的掛載名稱找不到,猜過的全部 404」。**這個結論是錯的** ——
使用者實測確認 LiveATC 聽得到台灣多數站台。

錯誤來自測試方法本身:當時只在 **單一節點** `s1-fmt2` 上試掛載名,而 LiveATC 的掛載點
分散在不同節點,打錯節點回 404 不能證明 feed 不存在;能指出正確節點的分派器
`d.liveatc.net` 又剛好被擋。一個沒有證據力的 404,加上一段搜尋引擎的摘要,得出了錯的
結論。**下次要否證某個 feed 存在,必須先從分派器或 .pls 拿到正確節點再測。**

原始(無效的)嘗試留作紀錄:`rctp_twr`、`rctp_app`、`rctp_gnd`、`rctp`、`rcss_twr`、
`rcss_app`、`rctp1`、`rctp2`。

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

## 2026-08-10 更正:分派器已被 Cloudflare 擋

原本第 1、2 點記錄「Cloudflare 只擋網頁,不擋串流,`d.liveatc.net` 可用」。現在:

```
http://d.liveatc.net/<任何掛載名>      → 403   (包含確定活著的 kjfk_twr)
http://s1-fmt2.liveatc.net/kjfk_twr   → 200 OK  icy-name: KJFK Tower 119.1
```

**直連節點仍然是純 HTTP、仍然可用**(對本專案避開 TLS 記憶體問題的價值不變),
但分派器不再能用來解析節點。這也讓「動工時要做的事」第 5 點的退路失效:
寫死節點失敗時,已經沒有 `d.liveatc.net` 可退。

## 真正的阻擋:LiveATC 服務條款

> Audio streams may not be used in any third-party products.

**這句話正對著本專案要做的事。** 關鍵不在技術而在散佈性質:這個專案有公開 repo、
Release 裡的預編 `.bin`、以及瀏覽器燒錄頁。只要韌體內建 LiveATC 網址,每一台燒進去的
裝置就是一個未經同意的第三方客戶端,直接連他們的伺服器 —— 而他們要保護的正是志工架的
接收機與頻寬。

這不是著作權問題(塔台通話本身通常不構成受保護的著作),是服務使用條款問題。
**自己用他們的網站或 App 聽,完全正常;把串流包進要發佈的韌體,是條款明文禁止的。**
差別在散佈,不在技術。

(先前這一節寫「個人裝置收聽在實務上與瀏覽器無異」,對一個公開散佈的韌體並不成立,已更正。)

### 三條路

1. **去問 LiveATC。** 他們有聯絡管道也個案授權過。非商業、開源、量小或許談得成。
   **唯一能光明正大內建 LiveATC 的路**,成本只是一封信。
2. **自架。** RTL-SDR + `rtl_airband` → 自架 Icecast → 裝置播區網 URL。
   完全沒有第三方條款問題(接收機與串流都是自己的),延遲與音質更好;代價是一台常開主機
   加一根天線。台灣法規上,自己收聽並只在自家區網內播,與「架站對外公開轉播」性質不同。
   **技術上與本文其餘部分完全相容** —— Icecast 天然是純 HTTP,MP3 解碼照樣由 ESPHome 內建。
3. **韌體只做通用 HTTP 串流播放器。** 不內建任何網址、不預設來源、文件也不提 LiveATC,
   就只是一個讓使用者自填 MP3/Icecast URL 的欄位(網路電台、Podcast 同樣適用)。
   **但這條只有在功能真的不是為 LiveATC 而設計時才成立** —— 一旦內建預設值或在文件裡
   教人填 LiveATC,就只是把違反條款的動作外包給使用者,性質沒有改變。

建議:先寫信問(成本最低、上限最高),同時把第 2 條當作不管對方怎麼回都可行的 Plan B。

## 評估過但不適用:OpenSky ATC API

`https://api.atc.opensky-network.org`(2026-08-10 查)。**不是音訊串流服務**,
拿來「聽」ATC 走不通:

- `/live/transcripts` 回 `text/event-stream` —— **即時的是「文字」轉錄,不是聲音**。
- 聲音只有歸檔錄音:`/audio-recording/airport|country|device|user/...` 列清單,
  `/audio-recording/share/...` 為單則錄音產生臨時公開網址。
- **全部端點需 OAuth2**(Keycloak implicit flow,scope `/opensky/atc/feeder`、
  `/opensky/atc/data`、`/opensky/atc/admin`)。未授權一律 401,連查機場清單都不行,
  因此**台灣覆蓋率無法在未登入的情況下驗證**。OpenSky 論壇的說法是餵音訊的人才有
  完整資料存取權 —— 與 ADS-B 那套「貢獻換額度」同一模式。
- 覆蓋率同樣是志工接收站決定的(`/receiver/all` 可依 airport / country 篩)。

值得留意的轉向:若台灣有站,`/live/transcripts` 對這台機器其實比音訊更合適 ——
不需要音訊管線,而且 `/receiver/callsigns` 顯示轉錄帶呼號標記,可以只顯示目前選取那架
飛機的通話,直接接進既有的航班詳情面板。代價是 SSE 長連線與現有「丟 job → 輪詢 ready
flag」的背景模式不同、必須走 HTTPS(又回到 TLS 記憶體壓力)、以及 headless 裝置上的
token 換發。
