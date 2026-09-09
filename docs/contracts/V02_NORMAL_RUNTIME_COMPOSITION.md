# 正常服务启动装配

范围：`yike-pilot-web` 服务端入口。依据[实施计划](../superpowers/plans/2026-09-10-normal-runtime-composition.md)，复用已实现服务，不新增一套框架或数据库。验证记录见[本片验收](../qa/V02_NORMAL_RUNTIME_COMPOSITION.md)。

## 正常入口

Web 使用同一个应用数据库构造 `PilotStore`、`ResearchStrategyStore`、`ExecutionRuntime`、`CandidateIngestionStore` 和 `CandidateReviewStore`，传给既有 `build_app`。执行和复核写路径使用同一个策略实例的 `resolve`；候选列表使用该实例的 `read_snapshot`。不再仅在测试中手工装配这些服务。

可使用现有认证接口准备、确认、读取与撤销策略，读取已有任务和候选、恢复原请求记录；配置模型后可走现有 ASSESS，再人工核验与纳入，取得共享商机原文证据。准备/确认策略不会启动采集，原始候选不是已核实商机，模型建议不是发送授权。

## 模型配置

部署者从仓库外受保护的服务器配置提供三项：

| 环境变量 | 含义 |
|---|---|
| `YIKE_PILOT_ASSESSMENT_BASE_URL` | 兼容模型 API 基地址；沿用现有适配器校验，非 loopback 必须 HTTPS |
| `YIKE_PILOT_ASSESSMENT_API_KEY` | 服务器模型密钥，不能放进客户端、Git、日志或导出 |
| `YIKE_PILOT_ASSESSMENT_MODEL` | 实际供应商支持的模型标识，不由系统猜测 |

三项均未提供或空白时，正常服务仍可读取和确认策略，但 ASSESS 返回 `501 capability_unavailable`。部分提供或格式非法时启动失败，只返回 `invalid_assessment_configuration`，不输出配置值。有效值原样交给现有模型适配器校验，不修改密钥或模型名。

复用现有 `OpenAICompatibleCandidateAssessmentModel`、固定版本 Skill、默认超时和每日调用上限；不新增无限额开关或自动重试。只有已认证、经现有授权与预算检查的 ASSESS 会调用模型。启动、能力读取、健康检查、列表和原请求恢复均不探测模型。模型实际输出质量需另验，配置合法不等于供应商已可用。

## 部署与权限

先由独立受信发布作业运行当前迁移及最小授权，再启动 Web；Web 不迁移、不 grant、不调用管理员连接 factory。沿用 [部署手册](../../deploy/README.md) 和现有身份/连接授权；执行、原始候选、复核、策略、证据分别需要 `grant_execution_runtime.sql`、`grant_candidate_ingestion.sql`、`grant_candidate_review.sql`、`grant_research_strategies.sql`、`grant_opportunity_evidence.sql`。

容器必须带入已有 `SKILL.md` 和 `qualification-and-evidence.md` 两份固定规则，位置与 wheel 的 `pilot/_assessment_rules/` 布局一致；Dockerfile显式复制这两份内容，不依赖完整开发仓库或运行时联网补文件。配置模型的源码启动、发行布局加载、实际Linux镜像与生产部署是不同验收层次。

非空 `YIKE_PILOT_ADMIN_DATABASE_URL` 被普通装配入口拒绝。该检查只阻止误带管理员环境，不验证 `YIKE_PILOT_DATABASE_URL` 实际指向的角色；非超级用户、非 owner、RLS、最小 ACL 及迁移状态仍须在部署环境核验。`/readyz` 只检查数据库连通，不能当作权限、模型或来源就绪证明。

## 仍未接通的能力

- 来源 policy：当前没有可用的生产来源安装/验收注册，执行服务仍使用 `capability_check=None`；新签名 START 返回 501。不能用 `enabled=true`、平台列表或测试回调绕过。
- 真实来源与 worker：构造入库服务不证明采集或新上传链可运行。历史记录可读，但不能凭此称为全网搜索已上线。
- 短信正常登录、搜索建议模型、平台发送及回复：本片不新增其配置或装配，既有默认能力保持关闭。
- 客户端与市场：桌面接入、真实来源/模型、确认后收发、Windows、生产与客户 UAT 另验，不由本片自动放行。

下一步直接推进来源执行和客户端消费这些现有接口，不再新建同类存储服务。完整 V1 Goal 保持进行中。
