# 动态公开研究接入客户链路

2026-09-13；基于 `ae94bf0` 后台源码和独立只读接线审计。状态：**范围内技术设计，部分内部基础已实现，客户纵切未完成**。沿已批准 V0.2 自主细化授权执行；不开放未经接通的新 capability，不把本设计当部署或客户验收。

接续：`1156c45` 已完成[内部逐动作宿主网关](../plans/2026-09-13-research-effect-gateway.md#evidence)并获独立审核通过，替代下文描述的 MCP 原文直连基线。context-v2、显式动态策略和客户快照 loader 已有[实现与限定证据](../plans/2026-09-13-customer-research-context.md#evidence)；同PG逐动作许可/journal在`b1e007a`独立审核通过，见[原始结果与未知回执证据](../plans/2026-09-13-durable-research-effects.md#evidence)。**动态客户能力合同与完整纵切仍未完成，不据此开放 capability。** MODEL replay绑定输入/工具配置及已校验、已恢复工具名的原结果，不接受任意字符串或二次别名恢复。

## 决策与第一条完整用户路径

选择复用 `ResearchExecutionService → ResearchResourceStore → ResearchRuntimeService` 和正式 PostgreSQL、现有候选/判断/复核，不建立第二套客户库。不把整段 `run_public_research_mission` 包成一次 SOURCE_READ，也不另开无预算的 customer→runner 路由。

第一纵切：客户正常登录 → 已确认画像 → 选择“公开网页自主研究”及用量/时效 → 原报价/签名 START → 国产模型形成查询 → 真实搜索发现非固定目录网址 → 宿主读取原文 → 同任务候选及证据入库 → 既有模型判断 → 客户查看出处并复核。可能产生 0 条合格商机；无自动外联，无客户 Codex 账号要求。原固定 V2EX 任务和专用平台连接器保持原行为。

## 显式合同，不偷换旧能力

- 新动态来源标识 `public-web-agent-v1`，单次 PUBLIC_WEB/PUBLIC_ANONYMOUS 任务。旧 catalog/sourcePlan/v1–v3 不自动升级，不把动态来源加入旧固定目录枚举。
- 新 runtime capability/status contractVersion=4，sourceScope=`PUBLIC_WEB_AGENT`，sourceLabel=`公开网页自主研究`；只在后端装配、逐动作许可、持久证据和客户消费均接通时发布。旧能力请求/严格 DTO 继续工作。
- 策略新增显式动态范围 `{version:1,maxAgeDays:1..365,timezone:IANA}`，仅新动态分支接受。前端初始建议 60 天、Asia/Shanghai，必须随策略确认；任务 reference_time 在服务端启动时固定，不能每轮重置或用搜索索引日期冒充原帖时间。
- 新能力明确用量含义：每次真正公网搜索、每次真正原文读取各占 1 次 SOURCE_READ，共用已确认 sources 上限；操作类型 SEARCH/READ 分开记录，搜索命中不是已读原文。模型规划、续接、总结和候选判断每次请求各占 MODEL_CALL。不新增或猜测搜贝售价/换算，缺有效报价规则则不可用。
- 动态 advance 是短请求启动/观察有界 supervisor，不继承旧“最多一个外部动作/advance”的宣称。页面关闭不删除后台账本；版本 4 页面必须单独说明已提交任务生命周期。旧页面本地暂停语义不修改。

## 服务端上下文与历史

新增薄 context store，只接受 authenticated claims + task_id/run_id，从现有任务/strategy/profile 锁与 digest 检查加载，不接受客户端上送 seller/history 或自报确认。固定上下文与规则版本/hash 保存于同一 PG 的任务附属记录。

- profile 描述来自 `business_profile_versions.payload.description`；当前合法输入可为 8,000 字并含换行，现有 context-v1 的 4,000 字/禁换行不兼容。新生产投影用显式 context-v2 接受合法多行 8,000 字、仍拒绝其余控制字符，不静默截断；保留原 profile hash 和实际投影 hash。旧 context-v1 调用兼容。总字节上限应覆盖合法字段上限，超限明确失败，不拆成无来源摘要。
- seeds/exclusions 使用已确认 configuration；行业 intentSignals/counterSignals/sourceTypes 保留。无行业 intentSignals 时用版本化 demandType→动作描述映射，不临时编造行业或许可范围。资料只用已有允许内部研究的引用；每次模型出站前重核撤销和画像/策略状态，不将完整私有资料一股脑导出。
- history 仅该 tenant + owner、同业务实体可见记录，稳定来源键/规范 URL 去重；人工排除、真实或人工登记联系、显式关闭分别有来源，不从草稿/复制/打开推导已联系。最多 30 条且稳定排序，截断为 PARTIAL；未加载为 NONE；只在实际完整读取时称 COMPLETE。不能按昵称合并项目。

## 所有外部动作经宿主许可

当前 MCP 原文读取直接在子进程出网，必须改成与搜索一样的私有宿主端口/随机 token 客户端；子进程不拿 DB DSN、claims 或模型/搜索供应商 key。保留 SSRF/DNS/跳转限制与本任务成功搜索 URL 白名单。

| 动作 | 接线点 | 准入与结果 |
| --- | --- | --- |
| 模型 | `ResponsesBridge._forward` 前后 | MODEL_CALL；上下文/模型配置/输入绑定；结果及实际 usage 持久化后再返回 Codex |
| 搜索 | `PublicSearchSession` 缓存之后、`_run` 之前 | SOURCE_READ + SEARCH；缓存重放不重复计量；搜索摘要不入原文候选 |
| 原文 | `research_tools.py` reader 改宿主 read endpoint | SOURCE_READ + READ；实际正文/hash/观察时间与许可一起提交 |
| 判断 | 既有 `assess_research` / before_dispatch | 沿用 MODEL_CALL、每日额度、出处绑定；预算不足保留待判断，不伪造合格 |

同一 PG 新增 owner-RLS 的有界 action journal：task/run/permit FK、operation kind、持久逻辑序号、coordinator generation、context/rule digest、无凭据的规范输入、有限结果/usage及继续状态。迁移编号在实施前以最新 main 分配，不在设计中抢号。现有资源表的 research_generation 固定 1，**不是 coordinator generation**，不得误用。

每次出站前经现有 begin + 当前 owner/generation/租约 admission；无事务跨网络。effective deadline 取 task/permit/租约/worker 上限最早值。取消/撤销/失租约阻止下一动作并回收子进程；已发请求不能假称撤回。结果未知或提交 ACK 丢失不重发、不自动退款。

已发生用量和原文事实允许按已准入 permit 补录，取消不抹账；但继续工作、下一动作、候选自动判断和任务完成须当前 generation。会话撤销后不能用管理员 DSN补记，需受控内部 scoped closeout 或保留 UNCERTAIN。首个纵切暂不承诺进程丢失后续跑 Codex 对话：保留事实并 STOPPED/UNKNOWN，不重启整段 mission。

## 原文与商机分离

复用 candidate sources/versions/observations/projections/batches，新增通用原文映射，不放松旧 V2EX index校验。只用实际 READ 的规范 URL、title、text、observed_at、content_sha256。external_source_id 用规范 URL 稳定 hash；published_at/author 无可信字段就为空，不能用模型/索引补事实。

读器最多 60,000 字、CandidateRecord.body 最多 20,000 字：超出候选合同的原文在有界 action evidence 留存并明确 oversize/未入候选，不能静默截断冒充完整原文。保留现有严格 research candidate execution_context，SEARCH/READ细节放 journal；若必须新形状则版本化 DB trigger，不往旧20-key对象随意塞字段。mission summary 不是 assessment 或人工复核。

## 接续工程批次及验收

1. **受控执行基础**：context-v2/客户loader、显式新策略合同、逐动作宿主网关、同PG action journal及取消/代次/UNKNOWN；新 capability 保持关闭。
2. **客户完整纵切**：通用候选原子提交、动态 supervisor/runtime/HTTP装配、客户端策略/报价/能力/状态v4；独立评审固定提交后一次候选构包，再做实际 customer→model→search→read→candidate→review 验收。
3. **专用平台补证与持续研究**：动态发现的受登录保护链接形成明确补查建议，进入原平台授权/确认/预算后才执行；不由PUBLIC_WEB许可隐式扩大平台targets。继续跨进程恢复、周期监测及跨行业试用，第一纵切不关闭完整Goal。

定向 PG/HTTP 验收：tenant/owner隔离、旧画像/策略和资料撤销、重复launch、每次出站前持久许可、额度耗尽无额外IO、SEARCH不伪装READ、UNKNOWN不重发、取消/失租约后旧worker不能继续/完成、原文/许可/候选原子性、超长/未知日期诚实处理、历史截断不称净新增。合成测试不代替实际平台和客户效果。
