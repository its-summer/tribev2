# TikTok Shop 服务商运营智能体系统（TSP / CAP / TAP）

面向 **TikTok Shop 官方服务商**的多客户代运营智能体框架。
我们是 TikTok Partner（TSP/CAP/TAP），agent 服务的是**我们的客户**，因此品类、商品、店铺均不固定——
系统按"**多租户**"设计：每个客户的店铺授权、品类、品牌调性、KPI 隔离在各自档案中，
agent 在执行任何任务前先加载对应客户上下文。

> 合规优先：作为官方 Partner，我们走 **TikTok Shop Partner Center 官方 API（OAuth 2.0 多店铺授权）**，
> 不使用模拟登录/群发/自动上传等违反平台 ToS 的爬虫工具。

---

## 一、整体架构

```
                       ┌─────────────────────────┐
   客户需求 ──────────▶│   orchestrator（调度中枢）  │
                       │  识别客户 → 加载档案 → 分派  │
                       └────────────┬────────────┘
                                    │
        ┌──────────┬───────────┬────┴──────┬───────────┬──────────┐
        ▼          ▼           ▼           ▼           ▼          
   short-video  livestream  creator-ops  shop-ops    ad-ops      
   短视频运营     直播运营    达人运营(CAP) 店铺运营(TSP) 广告投放(TAP)
        │          │           │           │           │
        └──────────┴─────┬─────┴───────────┴───────────┘
                         ▼
              skills（可复用专业知识 + 脚本）
                         ▼
        执行层 MCP / 官方 API（TikTok Shop Partner API、TikTok Business API、
                              Canva 出图、Gmail 外联、Notion CRM、Tavily 调研…）
```

- **调度中枢（orchestrator）**：入口。先确定"为哪个客户做事"，加载 `clients/<客户>/` 档案，
  再把任务分派给对应专家 agent，并把客户上下文注入。
- **5 个专家 agent**：每个对应一条运营板块/服务线，详见 `.claude/agents/`。
- **skills**：跨客户复用的方法论 + 检查清单 + 脚本，详见 `.claude/skills/`。
- **执行层**：官方 API / 已连接的 MCP 工具。详见 `integrations/`。

## 二、多租户：客户档案系统

每接一个新客户，从模板复制一份档案：

```
clients/
├── _TEMPLATE/            # 新客户模板（复制它）
│   └── client-profile.md
├── acme-beauty/          # 示例：某美妆客户
│   └── client-profile.md
└── ...
```

`client-profile.md` 是 agent 工作的"单一事实来源"：店铺授权信息、品类、目标市场、
品牌调性、合规红线、KPI 目标、当前重点。**任何 agent 动手前必须先读它。**

## 三、五大板块 → 服务线映射

| Agent | 板块 | 服务线 | 主要执行通道 |
|---|---|---|---|
| `shop-ops-tsp` | 店铺运营 | **TSP** | TikTok Shop Order/Product/Fulfillment/Promotion/Analytics API |
| `creator-ops-cap` | 达人运营 | **CAP** | Affiliate Creator/Campaign API、Gmail 外联、Notion 达人库 |
| `ad-ops-tap` | 广告投放 | **TAP** | TikTok Business/Marketing API、联盟 API |
| `short-video-ops` | 短视频运营 | 内容层 | 脚本引擎、Canva、short-video-maker(MCP) |
| `livestream-ops` | 直播运营 | 内容层 | 直播 playbook、TikTok-Live-Connector、复盘分析 |

## 四、如何使用

1. **接入新客户**：`cp -r clients/_TEMPLATE clients/<客户代号>`，填写 `client-profile.md`。
2. **完成 OAuth 授权**：按 `integrations/tiktok-shop-partner-api.md` 让客户通过 Partner Center 授权链接授权店铺，保存 token 引用到客户档案。
3. **派活**：对 orchestrator 说"给 acme-beauty 这周做一版短视频选题 + 店铺健康诊断"，它会加载档案并分派。

## 五、合规红线（所有 agent 必须遵守）

- 仅使用官方 API / 已授权 MCP，不做模拟登录、批量私信、自动刷量、虚假宣传。
- 客户店铺 token、客户数据严格按客户隔离，不跨客户混用。
- 涉及改价、上下架、投放预算、对外发送（邮件/私信）等**不可逆或对外动作**，先产出方案让人确认，不擅自执行。
- 广告与达人内容遵守 TikTok 社区规范与各目标市场的广告法规（功效宣称、价格、合规标签等）。

## 六、目录索引

- `.claude/agents/` — 6 个 agent 定义（1 调度 + 5 专家）
- `.claude/skills/` — 可复用技能（诊断、脚本、playbook…）
- `clients/` — 多租户客户档案
- `integrations/` — 官方 API 与 MCP 接入说明
