# 向上游提交说明（delphicchen/esp32_flight_radar）

> 目标仓库：https://github.com/delphicchen/esp32_flight_radar  
> 建议目标分支：`lvgl9`（与本 fork 血缘一致；勿直接打 `main`）  
> 提交人 fork：https://github.com/CaptainJi/esp32_flight_radar  
> **Merge 用分支：`pr/upstream-contrib`**（自检项已按第六节处理）

本文档供向原作者开 PR 时使用：说明改了什么、为什么、怎么测、哪些**不要**合进上游。

---

## 一、建议拆成的 PR（推荐）

上游更易 review 的方式是拆开，而不是一次扔整支 fork。

| PR | 主题 | 状态 | 建议标题 |
|----|------|------|----------|
| **A** | 雷达余晖 FADE | 已在 `pr/upstream-contrib` | `feat: FADE persist sweep (scan reveal + fade)` |
| **B** | 图砖图层扩展 + CDN 可配置 | 已在 `pr/upstream-contrib` | `feat: richer outline kinds + configurable maps CDN` |
| **C** | 地图/SYS/选中航班体验修复 | 已在 `pr/upstream-contrib` | `fix: map rebuild flicker, SYS panel, hold on dropouts` |

相关但不在本固件仓库内：

- 自建图砖 CDN：https://github.com/CaptainJi/flight-radar-maps  
- Pages：`https://CaptainJi.github.io/flight-radar-maps/v1`  
- **不要**把个人 `maps_base_url` 写进上游默认值；上游默认仍应是  
  `https://delphicchen.github.io/flight-radar-maps/v1`。

---

## 二、PR A — FADE 余晖扫描

### Summary

- 工具栏增加 **FADE**（MAP / ECHO / **FADE** / ATC / PWR / SYS）。
- FADE 开：扫描线扫过才显影，一圈内线性淡出；扫描更慢（约 24s/圈）。
- FADE 关：恢复常亮目标，扫描约 12s/圈。
- 余晖状态写入 NVS；修了 `slot_glow` 长度与槽位数不一致导致逻辑几乎不生效的问题。
- 扫描动画周期对齐 MIPI-DSI 面板刷新（约 16ms）。

### 为什么

接近真实一次雷达观感；原布局在六键并排下仍可用（按钮略缩、`font_tiny`）。

### Test plan

- [ ] P4 7B / S3 5B：开 FADE，目标随扫描显影并淡出
- [ ] 关 FADE：目标常亮，转速回到较快档
- [ ] 重启后 FADE 状态保持
- [ ] 点选航班在 FADE 下仍可辨认（保底透明度）
- [ ] ATC 开时向量/尾迹与余晖显隐一致（若已合入同步改动）

---

## 三、PR B — 图砖图层扩展 + CDN 可配置

### Summary

- Outline kind 从 0–2 扩展为 **0–5**：海岸 / 国界 / 省界 / 河流 / 公路 / 铁路。
- `tools/make_map.py` / `make_tiles.py`：增加 `--states/--rivers/--roads/--railroads` 数据源。
- 新增 `tools/build_china_map_tiles.sh`：示例生成华东/青岛周边格子。
- 固件增加 `substitutions.maps_base_url` → `-DRADAR_MAPS_BASE=...`，便于自建 Pages CDN。
- **兼容性**：旧 CDN 图砖只有 kind 0/1（或 0–2）时行为与现在一致；未知 kind 回退为省界配色。

### 为什么

官方 CDN 多为海岸+国界，中国区省界/河/路需自建图砖；固件侧需能画更多 kind，并允许换 CDN。

### 上游注意

- 默认 `maps_base_url` 保持官方地址。
- 若上游希望官方 CDN 也带省界，需另开 `flight-radar-maps` 的 tile 再生 + 发布（体积会变大）。
- `partitions.csv` 注释改为纯 ASCII，避免 Windows GBK 解析失败（可并入本 PR 或 C）。

### Test plan

- [ ] 默认官方 CDN：地图仍正常（无海岸/国界）
- [ ] 指向自建增强 CDN：可见省界/河/路配色分层
- [ ] 换坐标后会重新拉对应格子（见 PR C 节流修复）

---

## 四、PR C — 体验与稳定性修复

### Summary

1. **地图更新闪屏**  
   底图重建改为离屏画进 cache 再一次拷贝；重建期间 `lv_display_enable_invalidation(false)`，结束再统一 invalidate。

2. **SYS「失效」**  
   地图下载进度改写 `status_label`，不再占用右下 `sel_route_l`（与 SYS/天气/航线共用）。

3. **换坐标不更新地图**  
   5 分钟节流只作用于「同一 key 失败重试」，换坐标立即允许重抓。

4. **选中航班 `(out of range)` 误报**  
   用 ICAO24 + 45s HOLD：短暂丢星保留面板，超时才清空。

5. **airplanes.live 403**  
   冷却，避免刷屏失败（已在分支提交 `8d12564`）。

### Test plan

- [ ] 地图下载/重建时屏幕不再整屏猛闪
- [ ] 下载中开 SYS：系统信息不被 DOWNLOADING 盖掉；进度在状态栏
- [ ] 改 home 坐标后很快拉新图，无需干等 5 分钟
- [ ] 选中机短暂丢星显示 HOLD，不立刻 `(out of range)`
- [ ] airplanes.live 403 后不再每轮狂试

---

## 五、英文 PR 正文模板（可直接贴 GitHub）

### PR A

```markdown
## Summary
- Add FADE toolbar toggle: scan-reveal + fade (persist sweep), NVS-backed.
- Slow sweep when FADE on (~24s/rev); restore faster sweep when off.
- Fix slot_glow length vs AC_SLOTS so persist logic actually runs.
- Slightly denser toolbar (font_tiny) to fit six buttons.

## Test plan
- [ ] FADE on/off on P4 and one S3 board
- [ ] Persist survives reboot
- [ ] Selected aircraft remains visible under FADE
```

### PR B

```markdown
## Summary
- Extend outline kinds 0–5 (coast/country/province/river/road/rail).
- Tile generators: optional Natural Earth rivers/roads/railroads (+ states).
- `maps_base_url` substitution → `RADAR_MAPS_BASE` so forks can point at a custom Pages CDN.
- Default CDN URL unchanged (`delphicchen.github.io/flight-radar-maps`).
- Helper script: `tools/build_china_map_tiles.sh` for a China-enriched example set.

## Notes for maintainers
- Old tiles without kinds 3–5 keep working.
- Publishing richer official tiles is optional and belongs in `flight-radar-maps`, not this repo.

## Test plan
- [ ] Stock CDN still draws coast/borders
- [ ] Custom enriched CDN shows province/river/road layers
```

### PR C

```markdown
## Summary
- Stop map-rebuild flicker: offscreen cache + disable display invalidation while rebuilding.
- Move map download progress to status bar (was overwriting SYS/weather/route panel).
- Map fetch throttle only for same-key retries; coordinate changes refetch immediately.
- Selected flight: hex match + 45s HOLD instead of instant “(out of range)”.
- airplanes.live 403 cooldown (if not already upstream).

## Test plan
- [ ] Map update no full-screen flash
- [ ] SYS usable during map download
- [ ] Move home coords → new tiles without 5‑minute wait
- [ ] Brief ADS-B dropout shows HOLD, not out-of-range
```

---

## 六、提交前自检（给提交者）

1. **清掉个人配置** ✅  
   - `radar-p4-7b.yaml` **不再**写死个人 Pages；仅保留注释示例，默认走 `common/core.yaml` 官方 CDN。

2. **不要带进 PR 的内容** ✅  
   - `credentials.json` 已在 `.gitignore`；未纳入本分支  
   - 无 merge conflict 标记  
   - 不含 C3 圆屏实验分支 `feature/c3-round-radar`

3. **变基 / 开 PR**  
   ```bash
   git fetch upstream
   git push -u origin pr/upstream-contrib
   gh pr create --repo delphicchen/esp32_flight_radar --base lvgl9 --head CaptainJi:pr/upstream-contrib
   ```
   若希望拆成 A/B/C 三个 PR，再从本分支检出子分支并只保留对应文件/提交。

4. **图砖仓库**（可选第二轨）  
   若希望官方 CDN 也有中国增强层，另向 `delphicchen/flight-radar-maps` 说明再生方式与体积影响；本固件 PR 只需保证「能画 + 能换 CDN」。
   个人演示 CDN：`https://CaptainJi.github.io/flight-radar-maps/v1`（本地烧录可自行在 `radar-p4-7b.yaml` 临时覆写，勿提交）。

---

## 七、一句话给原作者

本 fork 在 `lvgl9` 上增加了 FADE 余晖、可扩展的图砖轮廓层与可配置 CDN，并修了地图闪烁、SYS 被下载进度盖住、换坐标不重拉、短暂丢星误报 out-of-range 等问题；默认官方 CDN 行为保持兼容，增强图砖可通过自建 Pages 使用。
