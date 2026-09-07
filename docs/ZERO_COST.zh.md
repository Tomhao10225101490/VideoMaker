# VideoMaker 零成本出片手册

本仓库是 [OpenMontage](https://github.com/calesthio/OpenMontage) 的 AGPL-3.0 衍生项目。默认把预算锁在 **$0**，不填任何付费 API Key 也能做视频。

上游英文文档仍以 [README.md](../README.md) 和 [AGENT_GUIDE.md](../AGENT_GUIDE.md) 为准。中文总览见 [README_zh-CN.md](../README_zh-CN.md)。来源与许可见 [NOTICE](../NOTICE)。

## 零 Key 能力

| 能力 | 免费工具 | 说明 |
|------|----------|------|
| 旁白 | Piper TTS（`zh_CN-huayan-medium`） | `make setup` 安装 `piper-tts`；中文语音下载到 `models/piper/` |
| 成片（React） | Remotion | 图文、数据卡、逐字字幕、旁白音轨 |
| 成片（HTML/GSAP） | HyperFrames | 动态字幕、产品片；需要 Node.js |
| 后期 | FFmpeg | 编码、混音、探测音量 |
| 开源实拍 | Archive.org / NASA / Wikimedia | 真正的运动画面，不是静帧 Ken Burns |
| 可选免费 BGM | Pixabay Music（无 Key） | 站点若 403，就只出旁白，不挡成片 |

**不要填** `FAL_KEY`、`OPENAI_API_KEY`、`ELEVENLABS_API_KEY`、`KLING_API_KEY` 等付费生成密钥，除非你明确接受账单。`config.yaml` 里 `budget.mode` 为 `cap`，`total_usd` 为 `0.00`。

## 官方 `make demo` 为什么没有声音

上游三支 demo 的 props 里是 `"audio": {}`。Remotion 仍会 mux 一条**静音** AAC，所以 `ffprobe` 看得到音轨，耳朵听不到旁白。那是视觉组件展示片，不是科普成品。

发视频平台的教育/科普内容，请走下面的图文解释片路径。

## 1–2 分钟中文科普（有声）

```bash
make setup
python scripts/zero_cost_preflight.py          # 会试合成一句中文并检查音量
python scripts/zero_cost_explainer.py fixtures/zero-cost/why-sky-is-blue.json
```

成片：`projects/why-sky-is-blue/renders/final.mp4`（gitignore）。验收记录见 [edu-proof.md](edu-proof.md)。

换选题：复制 [`fixtures/zero-cost/why-sky-is-blue.json`](../fixtures/zero-cost/why-sky-is-blue.json)，改 `id`、`title`、每段 `narration` 和 `cut`（`hero_title` / `text_card` / `stat_card` / `bar_chart` / `callout` / `comparison`），再跑同一条命令。

约定：

- 时长 60–120 秒；结构：钩子 → 3–6 个知识点 → 收束
- 画幅 16:9（B 站 / YouTube）。竖屏 9:16（抖音 / Shorts）本轮未改 Explainer 布局
- **旁白必须有**；BGM 可缺；**字幕必须有**（平台默认静音刷）
- 不要调文生图 / 文生视频

## 安装

依赖：Python 3.10+、Node.js 18+、FFmpeg。

```bash
make setup
python scripts/zero_cost_preflight.py
```

中文语音约 60MB，第一次出片会下载到 `models/piper/`（`*.onnx` 已 gitignore）。

## 官方无声 demo（仅验证画面）

```bash
make demo
```

探测记录见 [demo-proof.md](demo-proof.md)。

## 以后想花钱时

1. 在 `.env` 填入对应 Key
2. 把 `config.yaml` 的 `budget.total_usd` 调高，并确认 `mode`
3. 明确告诉 Agent 允许使用付费供应商
