# 跨境电商运营智能体矩阵

面向跨境电商运营的多智能体工作台。覆盖五大核心板块：**短视频运营、直播运营、达人运营、店铺运营、广告投放**。

## 路线图

| 阶段 | 形态 | 状态 |
|---|---|---|
| **Phase 1** | Claude Code 子智能体（`.claude/agents`）+ Skill（`.claude/skills`），逐模块跑通验证 | 进行中 |
| **Phase 2** | 迁移到独立多智能体后端（LangGraph / CrewAI），做成公司员工工作台 | 规划中 |
| **Phase 3** | 抽象为可按客户需求定制的对客产品 | 规划中 |

**平台推进顺序**：TikTok Shop → Amazon → 独立站（Shopify）。

## 架构

```
运营总管（主对话 / orchestrator）
├─ 短视频Agent   short-video-ops   选题·脚本·分镜·混剪·发布
├─ 直播Agent     live-stream-ops   话术·商品讲解卡·实时应答·复盘
├─ 达人Agent     influencer-ops    达人发现·初筛·外联·合作管理
├─ 店铺Agent     store-ops         选品·listing优化·定价·库存·数据分析
└─ 广告Agent     ad-ops            建广告·预算优化·素材·投放审计
```

每个 Agent = **子智能体定义（职责/SOP/调用边界）** + **一组 Skill（可复用方法论与脚本）** + **MCP 工具（连真实账号执行）**。

## 跨板块母版技能

- **`ecommerce-master-plan`**：对客「客户增长方案（master 方案）」的统一方法论与模板母版。第一性原理 `GMV = 流量 × 转化率 × 客单价`（三引擎）+ 分阶段 KPI 阶梯 + B2B 买家心理。**五大板块的客户方案都从它派生**（见技能内 `references/derivation-guide.md`）。沉淀自真实落地方案（MYTREX TikTok 日本直播增长方案）。

## 模块状态

| 板块 | 子智能体 | 技能 | 客户方案（从 master 派生） | 第一阶段验证 |
|---|---|---|---|---|
| 短视频运营 | ✅ `short-video-ops` | ✅ `tiktok-short-video` | ✅ 原理版模板 | ✅ 可跑通（选题→脚本→分镜，无需账号） |
| 直播运营 | ✅ 骨架 | ⏳ 待补 | ✅ 样例已沉淀（MYTREX） | ⏳ |
| 达人运营 | ✅ 骨架 | ⏳ 待补 | ⏳ 按母版派生 | ⏳ |
| 店铺运营 | ✅ 骨架 | ⏳ 待补 | ⏳ 按母版派生 | ⏳ |
| 广告投放 | ✅ 骨架 | ⏳ 待补 | ⏳ 按母版派生 | ⏳ |

## 可复用开源资产（调研结论）

第一阶段优先复用以下纯 markdown 技能包与 MCP，集成成本最低：

- **店铺/选品/跨境**：[nexscope-ai/eCommerce-Skills](https://github.com/nexscope-ai/eCommerce-Skills)（157 个电商 skill，含 TikTok Shop 平台指南）
- **达人外联**：[sales-skills/sales](https://github.com/sales-skills/sales)（influencer marketing / social listening）
- **广告投放**：[claude-ads](https://github.com/AgriciDaniel/claude-ads)（审计/优化 skill）、[ads-mcp](https://github.com/amekala/ads-mcp)（多平台广告 MCP）
- **短视频合成**：[short-video-maker](https://github.com/gyoridavid/short-video-maker)（自带 MCP）、[ShortGPT](https://github.com/RayVentura/ShortGPT)
- **直播数字人**：[LiveTalking](https://github.com/lipku/LiveTalking)、[Duix-Avatar](https://github.com/duixcom/Duix-Avatar)
- **营销全家桶**：[claude-marketing](https://github.com/thatrebeccarae/claude-marketing)

## 使用方式

在本仓库内用 Claude Code 直接对话即可，主对话作为"运营总管"按需派发给子智能体。例如：

> 帮我给这款保温杯做 5 条 TikTok 短视频选题和其中 1 条的完整脚本+分镜

会自动走 `short-video-ops` 子智能体 + `tiktok-short-video` 技能。
