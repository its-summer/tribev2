# shots.json 结构

整条管线的驱动文件。一份 shots.json = 一条视频。脚本拆镜后产出，逐步被各环节填充。

```json
{
  "project": "portable-blender-morning",
  "product": {
    "name": "Portable Blender 380ml",
    "ref_images": ["assets/product_front.png", "assets/product_side.png"],
    "selling_points": ["one charge 15+ blends", "30s blend", "cordless grab & go"]
  },
  "character_sheet": "assets/model_sheet.png",
  "market": "US",
  "language": "en",
  "aspect_ratio": "9:16",
  "bgm": null,
  "shots": [
    {
      "id": 1,
      "duration": 3,
      "shot_size": "close-up",
      "camera": "static, quick cut",
      "scene": "morning kitchen counter, soft daylight",
      "action": "one-tap start, smoothie blends in 2s",
      "voiceover": null,
      "subtitle": "A SMOOTHIE IN SECONDS",
      "first_frame_prompt": "",
      "first_frame_image": "",
      "video_clip": "",
      "needs_lipsync": false
    }
  ]
}
```

## 字段说明

- `ref_images` / `character_sheet`：一致性参考，全程复用。
- `needs_lipsync: true` 的镜头走 OmniHuman；其余走 seedance-cli i2v。
- `first_frame_prompt` → 文生图得到 `first_frame_image` → i2v 得到 `video_clip`，逐步回填。
- 管线脚本读这份 JSON，按 `id` 顺序执行并拼接。
