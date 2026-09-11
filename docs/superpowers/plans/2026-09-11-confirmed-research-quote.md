# 已确认研究策略的用量估算

> 执行：subagent-driven-development；V0.2内自主细化已授权，root统一提交、一次非作者整批审核。

**Goal:** 普通客户端以确认版本请求只读、可验证的资源上限估算，修改执行限制也会失效；服务端不能信任本机hash代替确认策略。
**Architecture:** 沿既有researchUsage保留历史TEST合同，正式传输增加必填strategyBinding；后端独立只读快照及签名凭证，无迁移、预留或START。缺显式规则或研究执行能力时501；本批不把普通采集能力冒充研究执行能力。
**Tech Stack:** Python/PostgreSQL/FastAPI与TypeScript/Zod/React。

## Global Constraints

- 正式POST `/api/ui/research-usage/quote`，固定桌面operation `researchUsage.quote`。请求精确字段：contractVersion:1、requestId规范UUID、userId、accountScopeId、accountScopeVersion:1、draftId非空最长512、revision正整数最多1000000、configurationHash小写SHA256、maxSoubei正整数最多1000000、strategyBinding:{strategyVersionId规范UUID,profileVersionId规范UUID,configurationSha256小写SHA256}。configurationHash为客户端编辑标识，仅原样绑定；服务端权威为strategyBinding。
- 响应回显全部请求，另quoteId规范UUID、ruleVersion非空最长512、ruleSha256小写SHA256、authorizationToken非空最长8192、estimatedSoubei非负不超过maxSoubei、generatedAt/expiresAt带时区ISO、basis非空最多2000。有效期固定300秒。token仅内存，不进日志/草稿/账本；它不是START授权的替代。
- 服务端规则是显式不可变`ResearchQuoteRule(ruleVersion, sourceMilli, minuteMilli, modelCallMilli)`，每项正整数≤1000000；无默认比例或环境自动启用。以`ceil((sources*sourceMilli + minutes*minuteMilli + modelCalls*modelCallMilli)/1000)`算资源上限估算，不称实际消耗预测，不用min截成客户上限；超上限409 usage_limit_exceeded。规则摘要使用规范JSON SHA256，签名HMAC-SHA256域分隔，密钥至少32字节，只由受信组装传入，不输出。
- `ResearchQuoteService(database, strategies, rule=None, signing_secret=None, research_capability=None)`。quote无业务写：认证活跃session，再独立RR READ ONLY、可信user/tenant scoped读`strategies.read_snapshot`；确认策略绑定的draft/revision需从同快照读当前版本行核对。精确核对user/scope、profile、配置摘要、maxSoubei、mode once和research存在。签名绑定完整响应（除token）、规则摘要/生效时间，verify函数拒绝篡改/过期/规则变化，用于后续原子START再核资格。
- research_capability由受信调用者对已确认snapshot判断，不从请求传入；缺rule/key/capability或返回非True时501 capability_unavailable。默认runtime仍None，不添加开启开关或伪执行器；仅注册新API和实际客户端服务，缺能力明确报错。测试显式合成规则/能力不代表生产可用。
- 服务端错误仅固定code/status，存储503、身份401、绑定409、不支持501；HTTPS、Origin、有限严格JSON体、重复字段拒绝与no-store继承现有边界。API服务为None时仍经过认证，不泄漏token。旧执行器及TaskWizard研究START保护不变。
- TS历史TEST `UsageQuoteRequest`/quote允许缺strategyBinding/ruleSha256；正式wire强制存在。新增实际服务标记`requiresConfirmedStrategy: true`；hook对该服务要求当前已确认策略，并在执行上限、确认版本、账号、草稿或服务变化时取消/失效。保留旧TEST恢复协议，不把签名token持久化。估算按钮在最终策略确认区也可用，客户无需返回修改步骤才能估算。

## Task 1：后端真实只读估算与API（独立实现）

Files：新增`pilot/research_quote.py`、`pilot/research_quote_api.py`，修改`pilot/ui_api.py`、`pilot/web.py`；新增`tests/test_research_quote.py`、`tests/test_research_quote_postgres.py`、必要API测试。不要改TS/docs/runtime配置或Git。

Interfaces：`ResearchQuoteService.quote(claims, raw_request) -> dict`；`verify(authorization_token, now=...) -> dict`返回已校验的完整非token响应用于后续START绑定（本批无START）；`register_research_quote_api(router, service, identity, require_session_https)`。build_app/register_ui_api增加可选research_quotes=None参数传递。

- [ ] RED：`assert service.quote(claims, request)["strategyBinding"] == request["strategyBinding"]`，带真实确认策略的受限PG；无模块先用find_spec断言正常失败，不以import错误作业务RED。
- [ ] 实现严格请求/规则、只读当前资格、上限计算和签名verify。旧服务无research或来源失效不能估算；当前确认快照必须与draft/revision匹配，不用客户端自报配置算费。输出basis说明是上限、未预留。
- [ ] 定向测试：上限数学/超上限、签名改字节/过期/规则改变、缺能力；真实PG确认→quote，跨user/tenant/hash/draft/revision/max拒绝、撤销来源/策略拒绝、只读业务表行数不变。API认证/Origin/HTTPS/no-store/严格体/不可用服务。只跑新测试及受影响接口，不构包/全量。
- [ ] 报告实际命令与RED/GREEN到`/tmp/yike-confirmed-quote-backend-report.md`；保留自建专用PG供root审核后停止，不触碰其他容器/服务器。root统一提交。

## Task 2：正式客户端确认版本估算链（root）

Files：新增`desktop/src/shared/researchUsage.ts`，修改现有domain/services/researchUsage、shared/contracts、main/servicePolicy、services/client、useUsageQuote、TaskWizard，以及定向tests。

- [ ] RED：`validatedOperation({operation:'researchUsage.quote',payload:request})`解析固定POST；缺strategyBinding拒绝；真实服务不发送整个draft。hook未确认不得调用，确认后请求带服务端SHA与执行上限，修改limits使迟到quote失效。
- [ ] 实现严格wire schema与服务；domain保留旧TEST字段，新增深比较strategyBinding与必须规则SHA核验；hook接确认状态，使用现有确认前重核，不改变旧START账本。
- [ ] 最后确认区提供同一估算动作，复制现有按钮样式而非改版；保存/恢复不保存token。定向Vitest+tsc，纯模拟UI不当实机/服务器证据。

## 验收与后续

本批两任务统一非作者审核，修复只看差量。正式默认服务缺研究执行能力仍不可估算，不能宣称可用完整研究；下一批接预算许可及原子START/资源事件，并实际启用同一服务后验收。价格及生产搜贝规则仍未获批准；本批无部署、外发、真实平台或Windows验收。
