# 候选待签字节最小接线验收

日期：2026-09-10。基线`bbe2e20`，计划/认领`2227389`，核心`805aeb0`。本片仅是普通客户端接续所需的后端工程能力，不是来源采集/平台发送/Windows/生产/客户验收。

## 范围

- 复用现有candidate签名域与4 MiB有界JSON入口，新增完整batch准备POST和五字段响应。
- 不新增SQL、依赖、nonce、预算预约、来源调用或自动触达；不改现正式ingest及回执优先恢复。
- 独立实现者只改3个现有后端文件和1个HTTP边界测试；root独占实际PG，编写真实主链测试并维护合同/交接。Win继续自己设备HTTP/worker/05G，不代记ACK。
- 合同：[上传/恢复/五字段](../contracts/V02_RAW_CANDIDATE_INBOX.md#11-普通客户端候选签名准备2026-09-10)；计划：[最小接线](../superpowers/plans/2026-09-10-candidate-submission-signing.md)。

## 本轮实际证据

| 验证 | 实际结果与边界 |
|---|---|
| 既有纯/边界基线 | `test_candidate_ingestion_api.py test_candidate_contract.py`：179 passed / 1.22s |
| root实际ASGI/PG RED | 新test文件`-k client_signs_response`：1 failed / 21 deselected / 1.41s；真实策略/START/CLAIM均已成功，新准备POST404 vs 200，非fixture失败 |
| root首次组合 | 1 failed / 26 passed / 27.74s；仅新测试误省必填`connection_id`，现DTO返回422 `INVALID_EXECUTION_CLAIM`正确，未更改产品校验 |
| 测试修正单验 | 仅省允许缺省的`connection_version`，1 passed / 21 deselected / 1.61s；随后单独核对键重排、缺省null，增加必填connection_id缺失拒绝 |
| root真实组合 | `test_candidate_submission_signing_http_postgres.py test_confirmed_strategy_http_postgres.py test_candidate_ingestion_http_postgres.py`：28 passed / 27.83s / 0 skipped；完整命令`uv run --frozen pytest -q`加上述三文件`--tb=short`，使用专用测试PG环境配置（凭据不写本文） |
| root生产范围收窄后最终组合 | 删除探索性的新增JSON深度walker，恢复原parser行为后的同三文件：**28 passed / 28.52s / 0 skipped**；不与上次相加 |
| root纯边界独立复验 | 四文件1 failed / 240 passed / 2.22s；仅深JSON测试的递归阈值假设与实际解析行为不符，fake服务返回200。交回实现者修正测试，不为fixture新增产品安全框架 |
| 独立实现者最终冻结 | 定向13 passed / 31 deselected / 0.56s；上述受影响四文件241 passed / 1.67s；深JSON改为未闭合输入验证原parse-error路径，不假称真实有效深JSON必须在传输层被拒绝 |
| root冻结片独立确认 | `test_candidate_ingestion_api.py test_candidate_contract.py test_execution_api.py test_execution_contract.py`：**241 passed / 1.77s**；与ASGI/PG集合分开记录。`git diff --check`、凭据扫描通过 |

根代理原误用不存在的`test_candidate_api.py`导致exit4/未运行测试，仅属命令路径错误，不作TDD RED或产品缺陷证据。以上集合包含重叠，不累加。

## 实际覆盖与未证明项

真实ASGI认证路由→真实当前策略→执行签名字节/Ed25519→START/CLAIM→候选待签字节→签服务端原UTF-8→实际事务入库→原回执恢复。客户端签名helper不构造tenant或session digest；测试检查摘要独立JSON规范化，不调用生产submission_signing_payload制造期望值。

覆盖五字段、Unicode正文空白、键顺序、可缺省null/必填null、空batch准备、同会话稳定/新会话旧签名拒绝、签后修改request_id/body/lease_id拒绝、同租户另一owner/跨租户/撤销设备/旧凭据拒绝。准备不调用来源/任务/策略/连接，admin受信查询候选五表/执行四表/key_requests/租约/records_used无新增变化；不用无scope应用RLS空结果假证无写入。

准备后取消、策略撤销、租约过期、预算耗尽仍在正式上传拒绝；设备撤销后准备拒绝，但原GET及无runtime情况下成功POST重放仍恢复历史，不重复计数。真实持设备行锁等待至session过期后401，无原文泄露。超100条/重复来源/未来时间/敏感URL/bool凭据/缺失必填字段被现业务校验拒绝，错误及日志无正文回显。

现有共享主链改用服务端候选原字节：真实策略→执行→候选→可控本地模型provider→人工核验/纳入→共享固定原文→策略撤销后的历史可读/新入库拒绝。输入仍合成，来源policy也是fixture；这些测试是TestClient实际ASGI+受限PG，不是socket/TLS、真实平台注册或线上客群效果。测试角色NOLOGIN/SET ROLE不替代部署账号独立登录ACL。

## 审核与接续

核心`805aeb0`的独立Task规格/质量**Approved，0 Critical/Important/Minor**。未改helper、middleware、实际PG等跨任务项由root实际28项与`PilotSessionRegistry.require_active`、`ExecutionRuntime._key`、`_UiRoute`及原ingest/fence逐项核对覆盖；没有通过新准备入口弱化原恢复或授权。root实际主链/文档`3d0ce80`，正常保留Win`0eab72a`的3份05G计划/依赖请求为`e47a925`，双方源码/测试/SQL/desktop未变化，未为纯文档合并重跑套件。

完整增量`bbe2e20..293fd24`经另一位非实现者整片终审：**规格/代码/架构/质量PASS，0 Critical/Important/Minor，可合并此工程片**。终审逐项核对owner/current key、DB时钟身份、原ingest历史优先/首写final fence、公共HTTP边界和可信测试计数；未重复测试、不扩大已验范围。7份变更Markdown的143个本地文件链接目标存在，凭据扫描与差异格式检查通过；不把链接存在当外部来源可用。

`626bbd97f648784611b4dbef2e4f9840890c4c17`已实际正常推送至`yike-ai2026/main`及`codex/mac-device-authorization`；独立ls-remote与本地HEAD精确一致，ahead/behind 0/0，工作树干净。与终审`293fd24`相比产品/测试/desktop/SQL/deploy无差异，收口只改3份事实记录文档；原工作区用户`docs/RUNBOOK.md`保持未动。本次文档回填不重跑无变化套件。

当前不是已验收上线。后续由Win按完整batch冻结、五字段核对、原字节签名、原复合键先查恢复来接worker/05G，取得其实际消费后才记ACK。最新Win新增请求已看到：INCLUDE回执补具体sourceVerificationId优先，设备登记未知结果按原ID恢复随后；本片不冒称已解决二者。

真实来源、平台账号、模型效果、确认收发、Windows发行与客户UAT仍须分别验收，父卡与Goal保持进行中。
