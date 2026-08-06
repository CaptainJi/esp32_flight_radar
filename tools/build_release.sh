#!/usr/bin/env bash
# 產生可發佈的韌體 —— 只編「當前分支負責的板子」。
#
# 用法:
#     git checkout main   && conda activate esphome        && tools/build_release.sh
#     git checkout lvgl9  && conda activate esphome-lvgl9  && tools/build_release.sh
#
# 刻意「不」自動切換 git 分支或 conda 環境:兩者都是全域狀態,而這個專案在
# 編譯途中被切走過好幾次(工具鏈找不到、拿錯分支的原始碼去編)。腳本只驗證
# 你已經切對了,切錯就直接拒絕跑。
#
# 產物放在 dist/,兩個分支各跑一次之後會湊齊四塊板子。dist/ 不進版控。
set -euo pipefail
cd "$(dirname "$0")/.."

# ---- 版本:git tag,沒有 tag 就退回 commit ----
VERSION="$(git describe --tags --always --dirty 2>/dev/null || echo unknown)"

# ---- 分支 → 板子對照 ----
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
case "$BRANCH" in
  main)
    WANT_ENV="esphome"
    # 入口:輸出檔名:晶片族(ESP Web Tools 的 chipFamily)
    ENTRIES=(
      "radar.yaml:s3-800x480-generic:ESP32-S3"
      "radar-s3-5.yaml:s3-touch-lcd-5:ESP32-S3"
      "radar-s3-5b.yaml:s3-touch-lcd-5b:ESP32-S3"
    ) ;;
  lvgl9)
    WANT_ENV="esphome-lvgl9"
    ENTRIES=( "radar-p4-7b.yaml:p4-touch-lcd-7b:ESP32-P4" ) ;;
  *)
    echo "錯誤:分支 '$BRANCH' 沒有對應的發佈板子(只認 main 與 lvgl9)。" >&2
    exit 1 ;;
esac

# ---- 前置檢查 ----
if [ -n "$(git status --porcelain)" ]; then
  echo "錯誤:工作目錄不乾淨。發佈的韌體必須對得回一個 commit。" >&2
  git status --short >&2
  exit 1
fi

CUR_ENV="${CONDA_DEFAULT_ENV:-<none>}"
if [ "$CUR_ENV" != "$WANT_ENV" ]; then
  echo "錯誤:分支 '$BRANCH' 需要 conda 環境 '$WANT_ENV',目前是 '$CUR_ENV'。" >&2
  echo "       先執行:conda activate $WANT_ENV" >&2
  exit 1
fi

command -v esphome >/dev/null || { echo "錯誤:找不到 esphome。" >&2; exit 1; }
echo "分支 $BRANCH / 環境 $WANT_ENV / 版本 $VERSION"
esphome version

mkdir -p dist

for spec in "${ENTRIES[@]}"; do
  IFS=: read -r ENTRY SLUG CHIP <<< "$spec"
  OUT="flight-radar-${SLUG}-${VERSION}"
  echo
  echo "==== $ENTRY  →  $OUT ===="

  # 每個入口用自己的建置目錄。四個入口的 ESPHome `name:` 都是 flight-radar,
  # 共用 .esphome/build/flight-radar/ 會互相覆蓋、每次都得全編;分開放才能沿用
  # 各自的快取。也與日常開發用的 build/ 與 build9/ 分開,不干擾手上的工作。
  # (這個變數是相對於 .esphome/ 的,不要寫成 .esphome/xxx。)
  export ESPHOME_BUILD_PATH="rel-${SLUG}"

  esphome compile "$ENTRY"

  SRC=".esphome/${ESPHOME_BUILD_PATH}/flight-radar/.pioenvs/flight-radar/firmware.factory.bin"
  [ -f "$SRC" ] || { echo "錯誤:找不到 $SRC" >&2; exit 1; }
  cp "$SRC" "dist/${OUT}.factory.bin"

  # ESP Web Tools 的 manifest。factory bin 是「含 bootloader + 分割表 + app」
  # 的完整映像,燒在 offset 0。
  # ESP Web Tools / esptool-js 的文件列出 ESP32-P4 為支援的 chipFamily,
  # 但我們沒有實際用瀏覽器燒過 P4;S3 是確定沒問題的。
  cat > "dist/${OUT}.manifest.json" <<JSON
{
  "name": "ESP32 Flight Radar (${SLUG})",
  "version": "${VERSION}",
  "new_install_prompt_erase": true,
  "builds": [
    {
      "chipFamily": "${CHIP}",
      "parts": [
        { "path": "${OUT}.factory.bin", "offset": 0 }
      ]
    }
  ]
}
JSON
  echo "→ dist/${OUT}.factory.bin  ($(du -h "dist/${OUT}.factory.bin" | cut -f1))"
done

# 校驗碼:每次只更新這一輪產出的檔案,另一個分支的產物保留
( cd dist && sha256sum flight-radar-*.factory.bin > SHA256SUMS )

echo
echo "完成。dist/ 目前的內容:"
ls -1 dist/
echo
echo "另一個分支的板子請切過去再跑一次:"
[ "$BRANCH" = main ] && echo "  git checkout lvgl9 && conda activate esphome-lvgl9 && tools/build_release.sh" \
                     || echo "  git checkout main  && conda activate esphome       && tools/build_release.sh"
