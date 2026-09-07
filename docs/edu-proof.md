# 有声科普片验证记录

官方 `make demo` 是无声展示片。有声路径：

```bash
python scripts/zero_cost_explainer.py fixtures/zero-cost/why-sky-is-blue.json
```

成片在 `projects/why-sky-is-blue/renders/final.mp4`（gitignore）。Pixabay BGM 本机返回 403/空结果，因此只有 Piper 中文旁白 + 字幕，没有背景音乐。

## 探测结果

| 项 | 值 |
|----|----|
| 时长 | 74.22s |
| 分辨率 | 1920×1080 30fps |
| 视频 | h264 |
| 音频 | aac stereo 48kHz |
| 音量 | mean **-19.5 dB**，max -3.0 dB（不是静音；静音约 -90 dB） |
| 体积 | 6.5 MB |
| 旁白 | Piper `zh_CN-huayan-medium`，wav mean -16.4 dB |

中间帧：

![why-sky-is-blue mid frame](demo-frames/why-sky-is-blue-mid.png)

`zero_cost_preflight.py` 中文试合成 `天空是蓝色的。` mean_volume **-13.5 dB**。
