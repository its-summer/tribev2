# LiveHuman — AI 数字人多语言直播平台

通过创建 AI 数字人，在 TikTok 上以多种语言进行 7×24 小时直播：自动生成口播内容、合成多语言语音、循环播放数字人形象视频并推流，同时实时读取直播间评论、用观众的语言即时回复。

支持两类数字人：

| 类型 | 来源 | 声音 | 形象 |
|---|---|---|---|
| **员工克隆数字人** | 员工录一段产品讲解视频，流水线自动生成 | 克隆员工本人声音，可说 30+ 种语言 | 员工真实录像（保留表情/动作），后续接实时口型同步 |
| 虚拟数字人 | 手写 YAML 配置 | edge-tts 公共音色按语言切换 | 任意形象循环视频 |

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

## 员工克隆数字人：从一段讲解视频到开播

```
员工录制产品讲解视频 (3~10 分钟, 竖屏, 安静环境)
        │
        ▼
┌──────────────────────────── creation/builder.py ───────────────────────────┐
│ 1. 授权校验    必须提供员工书面授权文件, 否则拒绝生成 (合规硬门槛)            │
│ 2. 素材提取    ffmpeg: 语音样本 wav + 形象循环片段 mp4                       │
│ 3. 声音克隆    ElevenLabs IVC → voice_id (克隆音色可直接说 30+ 种语言)        │
│ 4. 内容转写    faster-whisper 本地转写 (或 --transcript 提供文字稿)          │
│ 5. 风格提炼    Claude 从文字稿提炼: 人设画像 / 说话风格(口头禅) / 产品知识点  │
│ 6. 生成配置    personas/<员工>.yaml (含授权记录与来源元数据)                 │
└──────────────────────────────────────────────────────────────────────────┘
        │
        ▼
python -m livehuman.pipeline personas/zhangwei.yaml   # 用员工的数字人开播
```

```bash
export ELEVENLABS_API_KEY=...   # 声音克隆与克隆音色 TTS

python -m livehuman.creation.builder \
    --video recordings/zhangwei.mp4 \
    --name 张伟 --employee-id E1024 \
    --consent-doc consents/zhangwei_authorization.pdf \
    --languages zh en es \
    --loop-start 5 --loop-duration 20 \
    --out personas/zhangwei.yaml
```

设计要点：

- **声音**：克隆一次，多语言复用——员工录中文讲解，数字人能用"他自己的声音"说英语、西语、日语（`eleven_multilingual_v2`）。需要私有化时可平替为 GPT-SoVITS / CosyVoice / F5-TTS。
- **形象/表情/动作**：MVP 直接截取员工真实录像做画面循环，表情动作天然是本人的；下一步接 MuseTalk 实时口型同步（接口已预留在 `creation/lipsync.py`），口型即可跟随语音。
- **知识忠实**：Claude 只从员工实际讲过的内容里提炼话题池，系统提示词同时禁止编造参数/价格/承诺——数字人讲的卖点都是员工本人讲过的。
- **授权留痕**：persona YAML 里永久记录员工姓名、工号、授权文件、源视频和生成时间，可审计。

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
- **员工书面授权**：克隆员工的声音与形象前必须取得本人书面授权（生成流水线强制校验授权文件），授权书应明确使用范围、期限与撤回机制；员工离职或撤回授权后应停用其数字人。
- **不得仿冒真人**：数字人形象不得未经授权使用真实人物的肖像或声音。
- **各地区法规**：如中国大陆《互联网信息服务深度合成管理规定》等同类法规均要求对合成内容显著标识。

## 升级路线（Roadmap）

- [ ] **实时口型同步**：当前 MVP 用形象视频循环（行业常见做法）；下一步接入 MuseTalk / Ditto 等实时 lip-sync 模型，让口型跟随 TTS 音频（接口已预留：`creation/lipsync.py`）。
- [x] **声音克隆**：ElevenLabs IVC，克隆音色多语言发声；可平替开源方案私有化。
- [ ] **授权生命周期管理**：授权到期/撤回自动下线数字人。
- [ ] **商品讲解模式**：挂载商品列表，按脚本轮播讲解（直播带货）。
- [ ] **多房间并发**：一个实例管理多个数字人同时开播。
- [ ] **礼物/点赞事件响应**：感谢礼物、互动暖场。
- [ ] **Web 管理界面**：在 FastAPI 之上加前端面板。
