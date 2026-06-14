# AIGC 带货视频管线

把 `tiktok-short-video` / `tiktok-aigc-video` 产出的分镜（`shots.json`），自动生成全 AI 短视频成片。

```
脚本/分镜(shots.json)
  → 文生图: 逐镜首帧 (OpenAI gpt-image-1 / 火山Seedream)   [stage: frames]
  → 图生视频: 逐镜动起来 (火山 Seedance / Ark)              [stage: video]
  → 旁白: TTS 配音 (OpenAI audio.speech)                    [stage: voice]
  → 拼接: ffmpeg 合并 + 烧字幕 + BGM                         [stage: stitch]
```

> 口播对口型数字人（OmniHuman）暂缓——需另配字节 OmniHuman key。当前版本走"画面 + 旁白 + 字幕"。

## 为什么是可移植脚本而不是在本环境跑

当前 Claude Code 远程环境**出网受网关限制**（OpenAI/火山 endpoint 秒回 403），且 Seedance 是**国内火山** key、海外节点连国内本就受限。所以本管线设计为**在能出网的机器上跑**（你本地 / 国内服务器），本仓库只负责把代码与逻辑写好、`--dry-run` 验证流程。

## 用法

```bash
# 1. 装依赖（仅 ffmpeg；Python 用标准库，无需 pip）
#    macOS: brew install ffmpeg    Ubuntu: apt install ffmpeg

# 2. 设环境变量
export ARK_API_KEY="火山引擎 ark key"
export ARK_VIDEO_MODEL="doubao-seedance-1-0-pro-xxxx"   # 你账号的接入点ID
export OPENAI_API_KEY="sk-..."

# 3. 先 dry-run 验证流程（不调用任何 API，离线可跑）
python3 pipeline.py example_shots.json --dry-run

# 4. 真正生成（在能出网的机器上）
python3 pipeline.py example_shots.json --out ./output
# 也可只跑某一阶段： --only frames | video | voice | stitch
```

## 关键设计

- **一致性**：`character_sheet` 与产品 `ref_images` 全程作为参考图传入，逐镜复用，避免换脸/产品变形。
- **可断点续跑**：每阶段产物回写进 `shots.json`，失败镜单独重跑，不重跑整条。
- **零三方依赖**：HTTP 用 Python 标准库 `urllib`，`--dry-run` 仅需 python3。
- **平台可换**：`clients/` 下每个模型一个客户端，换 fal/Replicate/OpenAI 只改对应客户端。

## 文件

| 文件 | 作用 |
|---|---|
| `pipeline.py` | 编排器：读 shots.json，按阶段执行 |
| `clients/seedance_volc.py` | 火山引擎 Ark 图生视频客户端 |
| `clients/openai_image.py` | gpt-image-1 文生图/图生图 |
| `clients/tts.py` | OpenAI TTS 旁白 |
| `stitch.py` | ffmpeg 拼接+字幕+BGM |
| `example_shots.json` | 示例（榨汁杯，可直接 dry-run） |
