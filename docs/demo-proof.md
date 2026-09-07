# `make demo` 验证记录

成片写在 `projects/demos/renders/`（已被 `.gitignore` 忽略，不提交 mp4）。
中间帧截图保存在 [`demo-frames/`](demo-frames/) 作为肉眼证据。

命令：

```bash
make setup
python scripts/zero_cost_preflight.py
make demo
for f in projects/demos/renders/*.mp4; do
  echo "===== $f ====="
  ffprobe -hide_banner -show_entries format=duration,size,bit_rate:stream=codec_type,codec_name,width,height,r_frame_rate,nb_frames -of default "$f"
done
```

环境：Python 3.12、Node v22、FFmpeg 6.1.1、无 GPU、无付费 API Key。
`zero_cost_preflight.py` 退出码 0：`budget.mode=cap`、`total_usd=0.00`、付费 Key 均为空；Remotion / FFmpeg / HyperFrames 可用。

`make demo` 退出码 0，耗时约 233 秒。

## 探测结果

| 文件 | 时长 | 分辨率 | 视频 | 音频 | 帧数 | 体积 |
|------|------|--------|------|------|------|------|
| `code-to-screen.mp4` | 25.05s | 1920x1080 | h264 30fps | aac stereo 48kHz | 750 | 3.6 MB |
| `focusflow-pitch.mp4` | 22.55s | 1920x1080 | h264 30fps | aac stereo 48kHz | 675 | 4.1 MB |
| `world-in-numbers.mp4` | 23.06s | 1920x1080 | h264 30fps | aac stereo 48kHz | 690 | 4.2 MB |

三支片子均有视频轨和音频轨。各取 t=10s 一帧，亮度均值 38–54（不是黑屏）：

- [code-to-screen-mid.png](demo-frames/code-to-screen-mid.png) — 对比卡「9 files / 1 flow」
- [focusflow-pitch-mid.png](demo-frames/focusflow-pitch-mid.png) — 柱状图「Before 42 / After 18」
- [world-in-numbers-mid.png](demo-frames/world-in-numbers-mid.png) — 柱状图东京/德里/上海/圣保罗

原始 `ffprobe` 摘要：

```
code-to-screen.mp4
  Duration: 00:00:25.05, bitrate: 1180 kb/s
  Video: h264 (High), yuvj420p, 1920x1080, 30 fps, 750 frames
  Audio: aac (LC), 48000 Hz, stereo

focusflow-pitch.mp4
  Duration: 00:00:22.55, bitrate: 1493 kb/s
  Video: h264 (High), yuvj420p, 1920x1080, 30 fps, 675 frames
  Audio: aac (LC), 48000 Hz, stereo

world-in-numbers.mp4
  Duration: 00:00:23.06, bitrate: 1507 kb/s
  Video: h264 (High), yuvj420p, 1920x1080, 30 fps, 690 frames
  Audio: aac (LC), 48000 Hz, stereo
```
