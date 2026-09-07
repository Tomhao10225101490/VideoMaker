# 有声科普片验证记录

官方 `make demo` 是无声展示片。有声路径：

```bash
python scripts/zero_cost_explainer.py fixtures/zero-cost/why-sky-is-blue.json
```

成片在 `projects/why-sky-is-blue/renders/final.mp4`（gitignore）。Pixabay BGM 本机返回 403/空结果，因此只有 Piper 中文旁白 + 字幕，没有背景音乐。

口播按营销号短句重写（「先别划走」「重点来了」「等等」），`length_scale` 0.92、`sentence_silence` 0.12。画面 `motion_energy: high`：更快光斑、sparkles、光束、图文弹簧弹入。Piper 仍是同一把中文声，情绪主要靠稿子和切镜，不是付费配音。

## 探测结果

| 项 | 值 |
|----|----|
| 时长 | 77.23s |
| 分辨率 | 1920×1080 30fps |
| 视频 | h264 |
| 音频 | aac stereo 48kHz |
| 音量 | mean **-18.7 dB**，旁白 wav **-15.6 dB**（不是静音；静音约 -90 dB） |
| 体积 | 31.3 MB（粒子/光束每帧都在变，比静背景更大） |
| 旁白 | Piper `zh_CN-huayan-medium` |

钩子帧（「先别划走」+ 光束/闪点）：

![why-sky-is-blue hook](demo-frames/why-sky-is-blue-hook.png)

中间帧（瑞利散射柱状图 + 「短波先散」）：

![why-sky-is-blue mid frame](demo-frames/why-sky-is-blue-mid.png)

`zero_cost_preflight.py` 中文试合成 `天空是蓝色的。` mean_volume **-13.5 dB**。
