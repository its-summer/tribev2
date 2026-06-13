# LiveHuman — AI 数字人多语言直播平台

通过创建 AI 数字人，在 TikTok 上以多种语言进行 7×24 小时直播：自动生成口播内容、合成多语言语音、循环播放数字人形象视频并推流，同时实时读取直播间评论、用观众的语言即时回复。

## 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        FastAPI 控制台 (server.py)                 │
│        创建/管理数字人 · 启动/停止直播 · 查看运行状态               │
└────────────────────────────┬────────────────────────────────────┘
                             │
                  ┌──────────▼──────────┐
                  │  Pipeline 调度器     │  pipeline.py
                  │  (评论优先, 脚本兜底) │
                  └─┬───────┬─────────┬─┘
        ┌───────────┘       │         └────────────┐
┌───────▼────────┐ ┌────────▼────────┐  ┌──────────▼──────────┐
│ 内容生成 (Claude)│ │ 多语言 TTS      │  │ 评论监听              │
│ script_gen.py   │ │ tts/edge.py     │  │ tiktok_listener.py   │
│ chat_responder  │ │ (edge-tts,      │  │ (TikTokLive 库,      │
│ (流式+提示缓存)  │ │  40+ 语言)      │  │  无需官方 API)        │
└────────────────┘ └────────┬────────┘  └─────────────────────┘
                            │ PCM 音频
                  ┌─────────▼─────────┐
                  │ RTMP 推流          │  stream/rtmp.py
                  │ (FFmpeg: 形象视频  │
                  │  循环 + 实时音轨)  │──────► TikTok LIVE
                  └───────────────────┘
```

## 工作原理

1. **数字人 (Persona)**：每个数字人是一份 YAML 配置（`personas/`），定义名字、人设、直播主题、支持的语言以及每种语言对应的 TTS 音色，外加一段循环播放的形象视频（idle loop）。
2. **内容生成**：Claude（`claude-opus-4-8`）按人设持续生成口播脚本段落；收到观众评论时优先生成回复，并自动用评论的语言作答。人设系统提示词启用了提示缓存（prompt caching），长时间直播下成本大幅降低。
3. **语音合成**：`edge-tts` 免费支持 40+ 种语言/音色，按 persona 配置选择音色，输出解码为 PCM。
4. **推流**：FFmpeg 将形象视频无限循环作为画面，音频从管道实时写入（说话时写 TTS 音频，空闲时写静音），合成 H.264/AAC 推到 TikTok 的 RTMP 地址。
5. **互动**：`TikTokLive` 库监听直播间评论事件，进入回复队列。

## 快速开始

```bash
cd livehuman
pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...
export TIKTOK_RTMP_URL="rtmp://..."     # TikTok LIVE 的服务器地址
export TIKTOK_STREAM_KEY="..."          # 推流密钥

# 准备一段数字人形象循环视频（建议 10~30 秒、720p/1080p、竖屏 9:16）
cp your_avatar_loop.mp4 assets/aria_loop.mp4

# 命令行直接开播（使用示例数字人 Aria）
python -m livehuman.pipeline personas/aria.yaml

# 或启动控制台 API
uvicorn livehuman.server:app --host 0.0.0.0 --port 8000
```

需要系统已安装 `ffmpeg`。

### 控制台 API

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/personas` | 列出所有数字人 |
| `POST` | `/streams/start` | 启动直播 `{"persona": "aria"}` |
| `POST` | `/streams/stop` | 停止直播 |
| `GET` | `/streams/status` | 查看运行状态 |

## 重要：合规与平台政策

在投入运营前必须确认：

- **推流权限**：TikTok 的 RTMP 推流密钥仅对开通 LIVE 权限的账号开放（通常要求 1000+ 粉丝，或通过 TikTok Live Studio / 官方合作伙伴获得）。
- **AI 内容标识**：TikTok 社区准则要求对 AI 生成内容进行明确标注（开启 AIGC 标签），未标注的合成媒体可能被限流或封禁。
- **不得仿冒真人**：数字人形象不得未经授权使用真实人物的肖像或声音。
- **各地区法规**：如中国大陆《互联网信息服务深度合成管理规定》等同类法规均要求对合成内容显著标识。

## 升级路线（Roadmap）

- [ ] **实时口型同步**：当前 MVP 用形象视频循环（行业常见做法）；下一步接入 MuseTalk / Ditto 等实时 lip-sync 模型，让口型跟随 TTS 音频。
- [ ] **更自然的语音**：可替换为 ElevenLabs / Azure / MiniMax TTS（克隆音色）。
- [ ] **商品讲解模式**：挂载商品列表，按脚本轮播讲解（直播带货）。
- [ ] **多房间并发**：一个实例管理多个数字人同时开播。
- [ ] **礼物/点赞事件响应**：感谢礼物、互动暖场。
- [ ] **Web 管理界面**：在 FastAPI 之上加前端面板。
