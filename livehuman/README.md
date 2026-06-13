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

# 西班牙本土员工录西语讲解 -> 面向西语市场直播
python -m livehuman.creation.builder \
    --video recordings/lucia.mp4 \
    --name Lucía --employee-id E2031 \
    --consent-doc consents/lucia_authorization.pdf \
    --native-language es \
    --loop-start 5 --loop-duration 20 \
    --out personas/lucia.yaml
```

设计要点：

- **本土员工 + 母语录制**：尽量让目标市场的母语员工用母语录制。克隆音色会带录制者
  的口音，所以**母语默认就是该数字人的主直播语言**（`--native-language`），一个市场
  配一位本土员工最地道。详见 [`recordings/README.md`](recordings/README.md)。
- **声音**：克隆一次、多语言复用——克隆音色经 `eleven_multilingual_v2` 能说 30+ 种语言，
  但跨语言会带母语口音，适合做次要语言；主力市场用对应母语员工的数字人。需要私有化
  时可平替为 GPT-SoVITS / CosyVoice / F5-TTS。
- **形象/表情/动作**：MVP 直接截取员工真实录像做画面循环，表情动作天然是本人的；下一步接 MuseTalk 实时口型同步（接口已预留在 `creation/lipsync.py`），口型即可跟随语音。
- **知识忠实**：Claude 只从员工实际讲过的内容里提炼话题池，系统提示词同时禁止编造参数/价格/承诺——数字人讲的卖点都是员工本人讲过的。
- **授权留痕**：persona YAML 里永久记录员工姓名、工号、授权文件、源视频和生成时间，可审计。

## 按市场开放

数字人按市场组织，市场在 [`markets.yaml`](markets.yaml) 登记。每个市场有
代码、母语和状态：`active` 才能开播，`coming_soon` 为预留。**目前仅开放日本
（jp）**，其他市场（美国、西语区、韩国等）已预留，随业务扩张把 `status` 改为
`active` 即可放开。

开播流程内置市场护栏：数字人必须归属一个已激活市场，否则 `pipeline` 报错、
控制台返回 403。员工数字人在生成时通过 `--market` 归属到对应市场（见上一节）。

### 推流凭据归属到数字人

每个市场的数字人推到各自的 TikTok 账号、用各自的推流密钥，所以推流凭据下沉
到 persona 配置（而非一对全局环境变量）。在 persona YAML 里：

```yaml
stream:
  rtmp_url: rtmp://jp-live.tiktok.com/live   # 该数字人的推流服务器
  stream_key: ${JP_STREAM_KEY}               # 建议用密钥管理注入, 勿写死进版本库
  tiktok_unique_id: "@yuki_jp"               # 评论监听账号
```

解析优先级：**控制台请求显式指定 > persona.stream > 环境变量**。未配置 `stream`
的数字人（如演示用的 aria）继续走 `TIKTOK_RTMP_URL` / `TIKTOK_STREAM_KEY` /
`TIKTOK_UNIQUE_ID` 环境变量，完全向后兼容。这样单实例下切换数字人无需改环境
变量，将来转多路并发时每路天然有自己的推流目标，迁移几乎零改动。

## 快速开始

```bash
cd livehuman
pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...
export ELEVENLABS_API_KEY=...           # 声音克隆 / 克隆音色 TTS
export TIKTOK_RTMP_URL="rtmp://..."     # TikTok LIVE 的服务器地址
export TIKTOK_STREAM_KEY="..."          # 推流密钥

# 1) 用日本本土员工的讲解视频生成数字人 (归属 jp 市场)
python -m livehuman.creation.builder \
    --video recordings/yuki.mp4 --name Yuki \
    --consent-doc consents/yuki_authorization.pdf \
    --market jp --out personas/yuki.yaml

# 2) 开播 (jp 已激活, 通过市场护栏)
python -m livehuman.pipeline personas/yuki.yaml

# 或启动控制台 API
uvicorn livehuman.server:app --host 0.0.0.0 --port 8000
```

需要系统已安装 `ffmpeg`。

### 开播前预检与本地实跑

上线前先跑预检，把配置/环境问题一次性查出来（ffmpeg、形象视频、语音配置、
市场状态、推流目标、API Key）：

```bash
python -m livehuman.preflight personas/yuki.yaml
# 任一项 FAIL 退出码非 0, 可放进启动脚本/CI 做开播门禁
```

再做本地 dry-run，**不推 TikTok**，把 内容生成 → TTS → ffmpeg 合成 整条链路
录成本地 mp4，亲眼确认音画正常：

```bash
python -m livehuman.pipeline personas/yuki.yaml --dry-run 20 --out dryrun.mp4
```

### 稳定性

直播推流内置崩溃自愈：ffmpeg 意外退出会自动重启并带指数退避，已生成的口播
音频跨重启保留不丢；连续多次"启动即崩"（疑似配置错误）才放弃并记录原因。
这样网络抖动或 ffmpeg 偶发崩溃不会中断 7×24 直播。

> 示例数字人 `personas/aria.yaml` 是个英文虚拟形象, 仅用于测试内容生成与
> 语音合成; 它不归属任何市场, 因此当前不能开播 (市场护栏会拦截)——这正是
> 预期行为: 只开放日本时, 非日本市场的数字人不应上线。

### 控制台 API

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/markets` | 列出市场及状态、归属的数字人 |
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
