# VideoMaker 零成本出片手册

本仓库是 [OpenMontage](https://github.com/calesthio/OpenMontage) 的 AGPL-3.0 衍生项目。默认把预算锁在 **$0**，不填任何付费 API Key 也能做视频。

上游英文文档仍以 [README.md](../README.md) 和 [AGENT_GUIDE.md](../AGENT_GUIDE.md) 为准。中文总览见 [README_zh-CN.md](../README_zh-CN.md)。来源与许可见 [NOTICE](../NOTICE)。

## 零 Key 能力

| 能力 | 免费工具 | 说明 |
|------|----------|------|
| 旁白 | Piper TTS | `make setup` 会安装 `piper-tts`，完全离线 |
| 成片（React） | Remotion | 把图文、数据卡、字幕编成 mp4 |
| 成片（HTML/GSAP） | HyperFrames | 动态字幕、产品片；需要 Node.js |
| 后期 | FFmpeg | 编码、字幕烧录、混音 |
| 开源实拍 | Archive.org / NASA / Wikimedia | 真正的运动画面，不是静帧 Ken Burns |
| 可选免费素材库 | Pexels / Pixabay / Unsplash | 开发者 Key 免费，但不是必须 |

**不要填** `FAL_KEY`、`OPENAI_API_KEY`、`ELEVENLABS_API_KEY`、`KLING_API_KEY` 等付费生成密钥，除非你明确接受账单。`config.yaml` 里 `budget.mode` 为 `cap`，`total_usd` 为 `0.00`：估算大于 $0 的调用会被拦住。

## 三条免费路径

1. **Remotion 演示（本轮默认）** — 不写脚本、不调网络生成，直接渲上游自带的零 Key demo。
2. **图文解释片** — Piper 旁白 + 静图/图表，Remotion 做成动画（看起来像片子，不是付费文生视频）。
3. **纪录蒙太奇** — 从 Archive.org / NASA / Wikimedia 拉实拍，剪成时间线。提示词里写清「只用真实素材」。

本环境没有 GPU。本地 WAN / Hunyuan 文生视频不在零成本默认路径里。

## 安装

依赖：Python 3.10+、Node.js 18+、FFmpeg。

```bash
make setup
python scripts/zero_cost_preflight.py
```

没有 `make` 时，见上游 README 的手动安装命令。

## 第一支片子：官方 `make demo`

```bash
make demo
# 或只渲一支：
python render_demo.py world-in-numbers
python render_demo.py --list
```

三个零 Key Remotion 片子：

- `world-in-numbers` — 全球尺度标题、数据、图表
- `code-to-screen` — 开发工作流解释片
- `focusflow-pitch` — 只用 Remotion 组件的创业 pitch

成片路径（被 `.gitignore` 忽略，不要把大 mp4 提交进 git）：

```text
projects/demos/renders/world-in-numbers.mp4
projects/demos/renders/code-to-screen.mp4
projects/demos/renders/focusflow-pitch.mp4
```

用 `ffprobe` 检查分辨率、时长、是否有视频轨。探测记录模板见 [demo-proof.md](demo-proof.md)。

## 下一步（本轮不做）

- 用 Piper 做中文解释片（例如「为什么天是蓝的」）
- 用 Archive.org / Wikimedia 做 60–90 秒纪录蒙太奇
- 有 NVIDIA GPU 时再考虑 `make install-gpu` 本地视频生成

这些仍然可以 $0，但需要完整 pipeline（research → proposal → script → scene_plan → assets → edit → compose），并遵守 `AGENT_GUIDE.md`。

## 以后想花钱时

1. 在 `.env` 填入对应 Key
2. 把 `config.yaml` 的 `budget.total_usd` 调高，并确认 `mode`
3. 明确告诉 Agent 允许使用付费供应商
