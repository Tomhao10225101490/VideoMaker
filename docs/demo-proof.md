# `make demo` 验证记录

成片写在 `projects/demos/renders/`（已被 `.gitignore` 忽略，不提交 mp4）。

在 `make setup` 与 `make demo` 跑完后，用下面命令更新本页：

```bash
for f in projects/demos/renders/*.mp4; do
  echo "===== $f ====="
  ffprobe -hide_banner -show_entries format=duration,size,bit_rate:stream=codec_type,codec_name,width,height,r_frame_rate,nb_frames -of default "$f"
done
```

## 探测结果

_尚未渲染。setup / demo 完成后填写。_
