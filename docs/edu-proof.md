# 有声科普片验证记录

官方 `make demo` 是无声展示片。有声路径：

```bash
python scripts/zero_cost_explainer.py fixtures/zero-cost/why-sky-is-blue.json
```

成片在 `projects/why-sky-is-blue/renders/final.mp4`（gitignore）。Pixabay BGM 本机返回 403/空结果，因此只有旁白 + 字幕，没有背景音乐。

口播默认免费 **Edge TTS `zh-CN-YunxiNeural`**（与 [ai_video01](https://github.com/Tomhao10225101490/ai_video01) 同款，无 Key）：按句合成、钩子 `+18%` / 说明 `+10%`、WordBoundary 字幕、`voice_clarity` 后期（输出锁定 48 kHz，避免 `loudnorm` 的 192 kHz 在浏览器里静音）。断网回退 Piper。画面 `motion_energy: high`。

## 探测结果

| 项 | 值 |
|----|----|
| 时长 | 96.58s |
| 分辨率 | 1920×1080 30fps |
| 视频 | h264 |
| 音频 | aac stereo 48kHz |
| 音量 | 成片 mean **-21.6 dB**；增强旁白 **-18.6 dB** |
| 体积 | 38.6 MB |
| 旁白 | Edge TTS YunxiNeural，engine=edge |
| 字幕 | WordBoundary **313** cues |

钩子帧（「先别划走」+ 光束/闪点）：

![why-sky-is-blue hook](demo-frames/why-sky-is-blue-hook.png)

中间帧（瑞利散射柱状图）：

![why-sky-is-blue mid frame](demo-frames/why-sky-is-blue-mid.png)
