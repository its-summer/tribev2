---
name: tiktok-aigc-video
description: 用 AIGC 全流程生成 TikTok 带货短视频——脚本→逐镜提示词→AI 生成模特/道具/场景的分镜图→图生视频(Seedance)→口播数字人(OmniHuman)→拼接。当需要把短视频脚本变成全 AI 生成的成片，或设计/调用视频生成管线时使用。
---

# TikTok AIGC 带货视频管线

把 `tiktok-short-video` 产出的脚本/分镜，变成**全 AI 生成的成片**。核心难点是**跨镜头一致性**，解法是"分镜图优先"——先在图层面锁死人物/道具/场景，视频模型只负责让图动起来。

## 选型（默认主干）

| 环节 | 工具 | Key |
|---|---|---|
| 文生图（人物定妆照/分镜首帧） | Seedream / 即梦 | 自带 |
| 锁人物一致性 | seedance-cli 的 character sheet | Seedance key |
| 故事板拼版（人工审批） | Canva MCP | 环境已连 |
| 图生视频（主力） | **seedance-cli** | Seedance key（BytePlus ModelArk `ark-...`） |
| 口播数字人 | **OmniHuman 1.5** | Omni key |
| 补模型/快草稿 | LibTV（`npx skills add libtv-labs/libtv-skills`） | LibLib 积分 |
| 配音 TTS | ElevenLabs / 字节 TTS | — |
| 拼接字幕BGM | ffmpeg / short-video-maker | — |

> TapNow 仅作人工草稿，不进自动管线。

## 工作流（8 步）

1. **拆镜**：把脚本拆成 5–8 个分镜，每镜给：画面描述、景别、运镜、时长、是否需要口播。
2. **人物定妆照**：先生成 1 张主模特参考图（character sheet），锁定长相/服装/光影。**后续所有分镜复用这张做参考**，保证不换脸。
3. **逐镜首帧图**：以定妆照为参考，逐镜生成首帧图（模特+道具+场景）。用 `references/shot-prompt.md` 的提示词结构。
4. **故事板拼版**：用 Canva MCP 把首帧图拼成一张大图 → 交人工/客户审批节奏与一致性。
5. **逐镜图生视频**：用 seedance-cli 把每张首帧图 i2v，带运镜与原生音效。参数见 `references/seedance.md`。
6. **口播（可选）**：需要真人讲解的镜头，用 OmniHuman 给模特照 + TTS 配音对口型。
7. **拼接**：ffmpeg 按脚本时间轴拼接 + 烧字幕 + 加 BGM。
8. **合规复核**：套用 `tiktok-short-video` 的 compliance 清单再过一遍。

## 一致性铁律

- **人物**：全程用同一张 character sheet 做参考图，不要每镜重新文生图。
- **道具/产品**：产品图用真实产品照做参考（图生图），不要让 AI 臆造产品外观。
- **光影/色调**：定妆照阶段定下色温和风格，提示词里固定描述。
- **首尾帧控制**：相邻镜头用 Seedance 的首尾帧能力衔接，减少跳变。

## 产出

- `shots.json`：逐镜结构化清单（驱动整条管线，见 `references/shots-schema.md`）
- 分镜首帧图 + 故事板拼版图
- 各镜视频片段 + 拼接成片
- 合规复核表
