# 普通候选判断实际用量留存实施计划

> 使用 subagent-driven-development/TDD，按互斥文件分工执行；整批一次非作者复核。用户2026-09-11已授权既定V0.2内自行细化并开发，本计划不新增收费政策。

**Goal:** 普通候选ASSESS的实际provider tokens不再丢弃，调用失败/内容拒绝/过期时仍留存已收到的合法用量；缓存不重复计数，受认证只读接口能核对原调用。完整V0.2不以此子项结束。

**Architecture:** 复用已有原请求、快照、配额和重放。新增一份append-only、owner+tenant RLS的调用证据，DISPATCH在模型调用前短事务提交，FINISH在模型返回后独立短事务提交，再做原业务资格/结果提交。资料或会话撤销不能删除已发生的消耗，但不能借留存绕过撤销提供结果或再调用。普通用量与research resource许可不是两次消费，不新增自动重试或结算。

**Global Constraints:**
- 基线main `0eefff8c48faf9c71ffb5f2edab03393060878c1`，独占worktree `/tmp/yike-v02-scope.Pwf9Fs`、分支`codex/assessment-usage`。不部署、不联系用户、不调用真实模型，不修改其他runtime/Profile或服务器。
- 仅补普通ASSESS（snapshot没有research）；研究执行许可/用量计量路线保持，不能把普通tokens重复写成MODEL_CALL许可或搜贝。不定义价格、充值、余额、换算、退款。
- 用量沿用严格三整数prompt_tokens/completion_tokens/total_tokens，0<=n<2**31且前两者相加等于total；非法/缺失记unknown，不填0，不落额外provider字段。模型/规则/任务绑定来自原请求snapshot，客户端不能上报usage。
- `AssessmentModelError(code,status,*,usage=None)`增加仅内部属性usage（已校验三字段或None），str/repr和公开HTTP错误仍只有既有安全code。worker错误帧可选usage，父进程仍接受旧两字段错误帧，拒绝其他字段；原成功元组不变。
- 收到完整、有界、合法JSON provider envelope后，即使回答格式/证据不合法仍保留其合法usage；截断/超时未收到完整信息仍unknown，不能根据已生成字符估算。清理/父子时间门禁与无重试不变。
- 原请求status/snapshot/不可变触发器不放宽。新表`pilot_candidate_model_usage_events`每个原调用最多DISPATCH、FINISH两行，主键tenant/owner/request/phase，FK原请求，触发器拒绝alias/非ASSESS/attempt0，FINISH必须有DISPATCH，更新禁止。固定migration139追加，不改历史迁移。
- DISPATCH只证明进入受控调用边界，不证明provider收到请求或实际收费。FINISH outcome为SUCCEEDED/FAILED/UNKNOWN（模型输出判定），与最终业务入库资格分开。usage可为None。相同事件重复写入需一致，不得覆盖/累加；缓存/alias只读原调用，显式retry拥有新的requestId和事件。
- 调用前在当前资格核对通过后，使用活动会话短事务保存DISPATCH；失败则不调模型。FINISH仅由当前服务栈持有的捕获tenant/owner/request与snapshot_key写入，设置该捕获scope后校验原请求及DISPATCH；不靠当前profile资格才能留存，不提供任何客户端写接口。失败提交不重调模型，原业务返回outcome_unknown；已提交但ACK丢失可通过原请求查询恢复。
- 新GET `/candidate-review-requests/{request_id}/model-usage`沿用同一router前缀/HTTPS/session校验，首尾认证，禁止未知query参数；alias解析原invocation。DTO仅`schema_version:'candidate-model-usage-v1',requestId,invocationRequestId,candidateId,state,usage,outcome,recordedAt`。state为NOT_RECORDED（历史/未dispatch/研究独立路线，不等于免费）、PENDING（dispatch后仍在原deadline内未finish）、UNKNOWN（过期/无合法usage）、REPORTED（合法usage）；outcome和recordedAt无finish为null。不修改既有严格review/assessment返回合同。
- 不重做UI和研究计费。本批提供真实持久化与只读业务接口，客户端的用量呈现/跨任务汇总仍后续接入，不能宣称R4计量完成。

### Task 1: 模型用量安全穿透（root）

Files: pilot/candidate_assessment_model.py、pilot/candidate_assessment_worker.py；tests/test_candidate_assessment_model.py及新增定向用量测试。

- [x] 用有合法usage但非法回答的完整provider响应写RED；错误异常usage只保留三字段，未知不伪造，worker/parent旧帧兼容与新帧安全检查。
- [x] 在解析完整envelope后捕获validated usage；格式/grounding错误raise安全AssessmentModelError携带它；网络/超限无完整envelope不自造。保持现有业务错误code及超时语义。
- [x] worker错误帧只在usage合法时加usage，parent严格接收；定向pytest（使用既有Python `/tmp/yike-aliyun-sdk.DYc7GB/venv/bin/python`），不真实provider调用。

### Task 2: 持久化、原请求查询与隔离（独立backend Agent）

Files: 新migration139；pilot/db.py；deploy/grant_candidate_review.sql；新增pilot/candidate_model_usage.py；pilot/candidate_review.py、pilot/candidate_review_api.py；对应新tests/test_candidate_model_usage_postgres.py与API/必要fixture清理适配。不要修改Task1模型文件或桌面/其他文档。

- [ ] 写真实隔离PG RED：成功usage、None/invalid为UNKNOWN、非法回答仍有usage、缓存/alias仅一DISPATCH+FINISH、retry独立、调用中profile变化/撤销后仍留存但业务结果不得泄露、owner/tenant隔离、超时悬挂UNKNOWN、不可变事件和FK/alias拒绝。
- [ ] 按Global Constraints新增最小事件表与owner授权，不给UPDATE或DDL权限。迁移可重复应用。复用原请求快照的binding、模型元数据，不复制敏感输入进用量记录。
- [ ] 原普通调用前持久化DISPATCH、返回后先持久化FINISH再走原业务提交；捕获模型usage包括`getattr(error,'usage',None)`，验证错误不能擦除已返回usage。只追加真实本次事件，未dispatch不伪造FINISH。research分支保持现有流程。
- [ ] 新只读GET接正式认证，查询不触发模型/重试，不改变原返回合同。验证缺失/他人request和未知参数不会泄露。测试用固定synthetic model边界，真实PG事务/HTTP/权限；不要重跑整仓测试。
- [ ] 留报告含exact测试命令/结果、已知未验；不commit/push，由root整批冻结审核。

## 验收与接续

- [ ] Task1/2整合的真实PG+HTTP及模型worker定向验证；原配额/幂等/资格不可变规则保持。
- [ ] 固定SHA非作者审核，必要修复后差量复核，正常合main；不因本批再构包/部署。
- [ ] 文档记录本批实现及仍缺的普通客户端呈现/跨任务汇总、搜贝规则、真实模型生产计量、Windows/平台/跨行业客户验收。完整Goal ACTIVE。

## Evidence

Task1 新增行为先RED16失败（原异常无usage）；实现后新旧模型边界196通过，5.13秒。追加真实受控子进程→loopback HTTP返回非法回答+合法用量→worker错误帧→parent，确认只请求一次且usage穿透；最终增量17通过，0.93秒。测试使用合成输入及受控模型端点，不是生产模型计费证据。Task2真实PG/HTTP与整批审核尚待收口；不以Task1通过声明计量功能完成。

接续定向回归：迟到且非法的worker帧仍应记UNKNOWN，新增RED失败后补回父进程最终deadline门禁，已知usage不丢失。真实PG准备又暴露普通候选`_raw_model`把缺省source_context展开成显式null的生产回归；新增RED 1失败/2通过后，仅对原本缺省的CandidateRecord字段保留缺省，继续拒绝显式null和伪造bool，不以修改fixture掩盖问题。最终两份增量测试21 passed（1.10秒）。
