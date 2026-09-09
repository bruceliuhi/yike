# V02-02C：Win原始评论映射验收与交接

日期：2026-09-09；基线`67805826f4ad8df7d528899c4e61f2cda4407eb8`；代码提交`78116d9`；执行者CodexWin。规范：[已ACK的02A合同](../contracts/V02_CANDIDATE_INGESTION.md)；[实施计划](../superpowers/plans/2026-09-09-win-candidate-mapping.md)。本文仅覆盖原始字段到候选DTO，不是整张02C/02D完成或真实平台验收。

## 交付与接收边界

- 新增`connectors.candidate_mapping.build_comment_batch`：显式DOUYIN/BILIBILI、原始`content/comment`信封列表、request/profile/strategy版本、调用方execution声明、collector_version、query及可信now，返回现有正式冻结CandidateBatch。
- 直接保留原Unicode正文/父正文；匿名作者及未知发布时间为null。title有值优先，显式null仍未知，title缺失才用desc。公开作者字段按已定义命名空间优先选择，不采用creator_hash、昵称或主帖作者替代评论作者。
- 同义字段冲突、错主帖/评论ID、孤立父信息、缺实际观察时间整批拒绝；仅知道父ID时保留关系。父来源字段为Douyin的parent_aweme_id、Bili的parent_video_id/parent_aid，已提供时必须同源；父ID=0哨兵为无父评论。
- `observed_at`来自原始comment.collected_at，不从now/父时间/主帖时间补造。旧`app.collector._normalize_batch`会清掉此字段并自报verifiable，不能用于反推正式入站证据，也不得借其跨来源父查找补上下文。
- 已提供URL保留但须满足本切片明确支持的既有精确回链形状；缺URL才由校验ID构造。普通跟踪参数、别的定位形状也可能被拒绝，不能声称兼容全部平台链接；拒绝交调用方记录待补证，不得算无新增。构造回链不等于已实测能打开。
- 映射错误码`INVALID_RAW_COMMENT_BATCH`；现有正式校验错误码原样保留。正常输出只有DTO白名单；不产生tenant、reviewer、APPROVED、权限或运行授权。调用方不得记录原始payload。
- normalizer_version固定`raw-comment-candidate-v1`；原`connectors`入口、旧解析器、pilot服务/迁移、依赖锁、renderer及平台能力登记均未改变。

## 本机验证

Windows、CPython 3.11.14、仓库非editable受控环境；所有样例均为显式合成数据，没有访问真实账号、平台或模型。

| 检查 | 结果与范围 |
|---|---|
| 改动前相关基线 | candidate_contract/source_capabilities/connector_parsers：208 passed，0.32s |
| 实现者TDD | 首批256个明确缺实现断言RED→256 passed；超大整数`10**5000`单例再RED（1 failed/256 deselected）→修复后257 passed |
| 根代理独立消费TDD | 11个明确缺映射入口断言RED；正式JSON往返、身份字段拒绝、版本/指纹与模块导入随后GREEN |
| 根代理最新相关集合 | 476 passed，0.69s，0 skipped；含257映射、11消费、原208相关集合，不与下方历史集合重复相加 |
| 旧解析相关回归 | test_d03_remediation：31 passed、42 deselected，0.13s |
| 打包及导入 | 离线wheel构建成功；`python -I`直接从wheel导入新增模块，确认未加载app/sqlite3/psycopg；compileall通过 |

复现命令：

```powershell
./.runtime/venvs/win-device-review/Scripts/python.exe -X utf8 -m pytest -q tests/test_candidate_mapping.py tests/test_candidate_mapping_boundary.py tests/test_candidate_contract.py tests/test_source_capabilities.py tests/test_connector_parsers.py
./.runtime/venvs/win-device-review/Scripts/python.exe -X utf8 -m pytest -q tests/test_d03_remediation.py -k 'adapters or normalize_time or bilibili'
uv build --wheel --offline --python ./.runtime/venvs/win-device-review/Scripts/python.exe --out-dir .runtime/candidate-mapping-dist
```

打包文件（本机忽略目录）：`.runtime/candidate-mapping-dist/yike_discovery_mvp-0.1.0-py3-none-any.whl`；SHA-256：`5fa048fab932aa129dc28c1d796d59ff4eeb76cc4338a3d48ab99fefbaee40e3`。

## 独立审核及下一接入

- 规格审核：win_contract_readiness直接阅读新模块和两测试文件，PASS；模块SHA-256 `df2dd3e00a8e201218db98e61a660d2d2e45be95f5823f990fd6d7068394a43f`，实现测试`8c157dedd8ded1fa2a32a30509bc1e955fa80f8a7d1d31c2ee0235656c213b80`，独立消费测试`34c8217762c8305142d2eb19de28b03870427f21754037524c6ada13095be730`。
- 代码/架构/质量：supplychain_readiness独立审核PASS，三文件摘要与上述规格冻结值一致；独立复跑同组476 passed/0.67s，旧解析31 passed/42 deselected/0.10s，无新增P1/P2。代码提交`78116d9`包含这三个已审文件，不把根代理检查冒作独立审核。
- 接收：通过main向Mac交接可消费的DTO映射，尚无Mac对此映射的实际ACK。Mac的01C/02B/03A及R4页面没有在本映射提交中被修改。
- 仍缺：真实采集执行与原始观察时间传递、上传/持久化、主帖/网页及其余来源适配、逐平台样本和整链验收。capability仍未解锁，不以纯映射成功冒称已发现真实商机。

下一条功能线已按源码确认现有单业务画像保存/确认可复用（pilot/store.py、ui_api.py及renderer/services/client.ts），04B可直接从已确认版本继续，无需先重做完整多业务管理；生产suggest仍不可用。此结论为源码接入调查，不是本轮重新运行PG或完成策略服务的证据。

## 同轮保留Mac最新主线

正常整合远端`3a51a2f66ee55b24f7e6406a9f2508cb30e1d65f`，没有覆盖其107连接版本、进程停止、Node冷启动夹具及R4/分期文档。Mac已在该提交实际ACK 04A/B→05B/C分工，明确不重复实现；共享ui_api/db/store由Win提供最小补丁、Mac串行集成，108仅预留给需要时的首个资料/画像迁移。该分工ACK不等于本映射ACK或新接口验收。

合并工作树定向验证：原476＋连接版本纯契约23＝499 passed/0.80s，旧解析31 passed/42 deselected/0.11s；这里不是新增PG接收。Node24.19下`node node_modules/vitest/vitest.mjs run tests/windowsBuildRuntime.test.mjs`为36 passed/1既有非x64条件skip，11.91s。首次误用`node --test`启动Vitest文件，因缺Vitest suite报错（退出1）；检查文件导入及package脚本后仅纠正命令，未改代码或将该次调用错误隐去。

此次未重跑Windows完整打包、连接版本真实PG或Linux进程生命周期，未给01C-CV/10E-PROC新的完整Win ACK。其Mac自带1037/630结果仍只属于Mac，不与本次结果相加。
