# 执行层：MCP 工具与开源选型

各 agent 的"手脚"。原则：**官方 API / 官方 MCP 优先；开源只用成熟、合规的；坚决不用模拟登录/刷量/群发类爬虫**（封号风险 > 收益）。

## 一、本环境已连接、可直接用的 MCP
| 工具 | 用途 | 服务 agent |
|---|---|---|
| Canva | 封面/海报/图文/视频模板出图 | short-video-ops、shop-ops |
| Gmail | 达人合规外联邮件（先审批） | creator-ops-cap |
| Notion | 达人 CRM、客户 SOP、知识库 | creator-ops-cap、orchestrator |
| Google Drive | 客户素材库 | 全部 |
| Google 日历 | 直播/发布排期 | livestream-ops、short-video-ops |
| Tavily | 趋势/对标/竞品实时调研 | short-video-ops、ad-ops |

> 注意：本环境的 Shopify MCP 与本业务无关（我们做 TikTok Shop），不使用。

## 二、需自建 / 接入的官方通道
| 通道 | 用途 | 状态 |
|---|---|---|
| TikTok Shop Partner API | 店铺/订单/促销/达人/数据 | 需自建 MCP（见 tiktok-shop-partner-api.md） |
| TikTok Business/Marketing API | 广告投放 | 需接入，可参考官方 SDK |

## 三、可选开源（成熟 & 合规范围内）
| 项目 | 用途 | 备注 |
|---|---|---|
| [gyoridavid/short-video-maker](https://github.com/gyoridavid/short-video-maker) | 口播+字幕+素材合成短视频，原生 MCP | ✅ 推荐，内容层原型 |
| [tiktok/tiktok-business-api-sdk](https://github.com/tiktok/tiktok-business-api-sdk) | 官方投放 SDK | ✅ 官方 |
| [ipfans/tiktok](https://github.com/ipfans/tiktok) | TikTok Shop 开放平台 Go SDK | ✅ 参考 |
| TikTok-Live-Connector | 直播间公开互动事件流（只读） | ⚠️ 仅取数辅助复盘，不做自动化干预 |

## 四、明确排除（合规红线）
- 模拟登录自动上传器（tiktok-uploader / TiktokAutoUploader 等）
- 达人私信群发 bot（Affiliate-Outreach-Bot 等）
- 任何刷量、养号、批量操作脚本

外联走官方 Affiliate 邀约或 Gmail；发布走官方排期或人工。
