# seedance-cli 图生视频参数

BYO key（BytePlus ModelArk `ark-...`）。安装：`cargo install seedance` / Homebrew / GitHub Releases。先 `seedance doctor` 验 key。

## 鉴权

```bash
export SEEDANCE_API_KEY="ark-..."   # 或 config 文件 / --api-key
seedance doctor                      # 验证凭证
```

## 图生视频（管线主用法）

```bash
seedance image-to-video \
  --image assets/shot3_first_frame.png \
  --prompt "中近景，手部倒入水果后一键启动，轻微推近运镜，原生环境音" \
  --duration 5 \
  --resolution 720p \
  --aspect-ratio 9:16 \
  --json                              # 机器可读，便于脚本编排
```

## 关键能力

- **image-to-video**：0–9 张参考图（含 character sheet 锁人物）。
- **first-and-last-frame**：相邻镜头衔接，减少跳变。
- **character sheet**：跨镜头身份一致。
- **原生音效**：Seedance 2.0 可同生环境音/音效。
- 输出 480p / 720p，按秒计费（约 $0.05/5s 720p）。

## 脚本编排约定

- 全程加 `--json`，用退出码（0 成功，非 0 各类失败）驱动重试。
- 每镜产物落到 `shots.json` 的 `video_clip` 字段。
- 失败镜单独重跑，不重跑整条。

> 若 Seedance key 来自火山引擎(国内)或 fal，而非 BytePlus，则改用对应 SDK/endpoint —— 确认 key 来源后再定具体客户端。
