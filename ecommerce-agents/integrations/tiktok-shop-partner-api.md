# TikTok Shop Partner API 接入说明（服务商多店铺）

作为 TikTok Shop 官方 Partner（TSP/CAP/TAP），我们通过 **Partner Center 官方 API** 合规地代客户运营多家店铺。本文档是 agent 执行层的接入依据。

> 当前环境**尚未连接** TikTok Shop 的 MCP server（Shopify MCP 已连接但与本业务无关）。
> 落地有两条路：(A) 自建一个 TikTok Shop Partner API 的 MCP server；(B) 用官方 SDK 写脚本沉淀到 skills。推荐 A，便于所有 agent 复用。

## 1. 角色与可用 API

| 角色 | 主要 API 域 |
|---|---|
| TSP（店铺） | Product、Order、Fulfillment、Logistics、Promotion、Finance、Analytics |
| CAP（达人） | Affiliate Creator、Affiliate Campaign / Target Collaboration、Affiliate Order |
| TAP（投放/联盟） | TikTok Business/Marketing API、Affiliate 数据归因 |

## 2. 授权流程（OAuth 2.0，多客户隔离）

1. 在 [TikTok Shop Partner Center](https://partner.tiktokshop.com/) 创建 App（Custom app 用于直接服务指定卖家；Public app 用于上架应用市场），拿到 **App Key / App Secret / Service Id**。
2. 生成授权链接发给客户；客户在 Partner Center 授权店铺给我们（权限范围与时长可控，最长 1 年）。
3. 处理授权回调拿 `auth_code` → 换取 `access_token` + `refresh_token`。
4. **按客户隔离存储 token**（密钥管理服务/加密存储），客户档案中只存"引用/路径"，绝不明文写 token。
5. 用 `Get Authorized Shops` 拉取该 App 下所有已授权店铺，与客户档案的 shop_id 对应。
6. token 到期前用 refresh_token 刷新；监控授权到期日（记入客户档案）。

参考官方文档：
- 授权指南：https://partner.tiktokshop.com/docv2/page/authorization-guide-202309
- 授权总览（202407）：https://partner.tiktokshop.com/docv2/page/678e3a3292b0f40314a92d75
- 获取已授权店铺：https://partner.tiktokshop.com/docv2/page/get-authorized-shops
- 开发者指南：https://partner.tiktokshop.com/docv2/page/tts-developer-guide

## 3. 调用规范
- 所有请求按官方签名规则（app_secret 计算 sign）+ access_token。
- 多店铺：每次调用绑定具体 shop 的 token，**严禁跨客户复用 token**。
- 遵守接口频率限制；批量操作分页、限速、可重试。

## 4. 建议的 MCP server 工具划分（自建时）
- `tts_get_authorized_shops`、`tts_get_products`、`tts_update_product`、`tts_get_orders`、`tts_get_order_detail`、`tts_get_shop_performance`、`tts_create_promotion`、`tts_get_affiliate_creators`、`tts_invite_creator`、`tts_get_ad_report` …
- 写操作（改价/上下架/促销/邀约/起投）在工具层加"need_confirm"标记，配合 agent 报批铁律。

## 5. 合规
- 仅在客户授权范围与有效期内操作。
- 客户数据按租户隔离、最小权限、加密存储。
- 不绕过官方 API 做任何抓取/模拟操作。

## 6. 相关官方 SDK / 参考
- TikTok Shop 开放平台 Go SDK：https://github.com/ipfans/tiktok
- TikTok Business API SDK（投放）：https://github.com/tiktok/tiktok-business-api-sdk
- 短视频生成 MCP（内容层）：https://github.com/gyoridavid/short-video-maker
