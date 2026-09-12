# 作者更新完整纵向交付计划

> 使用subagent-driven-development执行；用户要求压缩重复审核，整批一次非作者审核。

**Goal:** 固定项目源的作者更新进入普通候选原文和模型判断。
**Architecture:** 按[设计](../specs/2026-09-11-public-author-context-design.md)的唯一字段合同复用JSON内容版本、普通执行和确认，不建第二线索库。
**Tech Stack:** Python/Pydantic/PostgreSQL；TypeScript/Zod/React/Node fetch。

## Global Constraints

全部精确字段、限制及枚举以设计为准。旧任务不扩请求/权限；旧内容hash不变；不部署/构包/发送，不调用付费模型。先RED后实现；非作者审核一次整批。工作树已隔离且干净，基线11a640b。

## Task 1: 后端合同与模型/能力

- [x] 在tests新增source_context合法/错配/超限/旧hash/模型引用的定向失败测试。
- [x] 修改pilot/candidate_contract.py、candidate_ingestion.py持久可选上下文；candidate_review.py投影author_updates/scope；candidate_assessment_model.py严格验证与引用/规则版本。未携上下文的旧输入保留旧字段。
- [x] pilot/research_strategy_contract.py、foreground_collection.py、monitor_runtime.py及模式CLI注册增加新源/新模式；旧mode目录不能扩大；research拒绝新源。
- [x] 跑涉及的新测试/旧模型和来源合同；一次隔离PG上下文版本联验。无真实模型请求。报告具体命令及结果。

## Task 2: 客户端与真实来源

- [x] 先新增publicCommunityDriver/上传与raw evidence/模型DTO/原文视图定向测试并见RED。
- [x] shared source_context独立schema复用于上传/raw；内容对照和时间检查纳入context；candidateReviewApi引用允许author_updates索引。
- [x] source目录/任务限制支持显式新源；driver有界索引+作者回复读取，保留统一deadline/bytes/cooldown；原文视图显示更新/缺口，来源label暴露范围。
- [x] 定向vitest和tsc；一次真实只读driver，不以mock或模型判断代替真实数据证据。

## Task 3: 整合

- [x] 对照两端合同及旧值字节，复用旧HTTP链并做定向PG/TS验证；本批未做真实来源→HTTP→PG一体联验，不全量构包。
- [x] 非作者审核固定提交，必要差量修复；记录更新后按正常非强制合并推送main，远端结果以任务书接续为准。

## Evidence（2026-09-11～12）

实现候选 `47416bdd65ecd18f06c248ce0bc2d4371e9b1c9c`。以下为各阶段定向结果，存在重叠，不能相加宣传总覆盖率。

- Python：`pytest -q tests/test_public_author_context_backend.py tests/test_candidate_contract.py tests/test_candidate_assessment_model.py tests/test_public_collection_policy.py tests/test_public_node_collection.py tests/test_foreground_collection.py tests/test_opportunity_evidence.py tests/test_source_content_changes.py -k 'not restricted_http'`，437 passed / 1 deselected。后续严格false、捕获证据重验差量13项；三源默认/目录及旧node策略10项；未知主帖时间与旧batch指纹3项。根侧最终 `pytest -q tests/test_public_author_context_backend.py` 28 passed。
- 隔离PG：`test_public_monitor_postgres.py::test_public_author_context_round_trips_and_creates_content_version` 1 passed；合成数据实际保存、当前/历史重开及作者更新生成新版本。测试库容器使用后停止，不涉及客户/生产数据。
- 客户端：publicCommunityDriver/publicAuthorContext/public-author-evidence/rawCandidateEvidence/candidateReviewApi 257 passed；候选引用UI、来源服务/controller/monitor/selector 86 passed；来源选择/controller/快照差量71 passed；纳入机会证据解析及UI 36 passed。最终兼容三源目录的foregroundCollectionController 53 passed；跨响应共享字节/截止时间2 passed；`tsc --noEmit`通过。
- RED已覆盖：新来源驱动8失败、原文schema/UI2失败、作者引用UI1失败；后端合同/能力3失败、模型投影1失败、缺失索引及变化提示2失败；集成检查另暴露旧指纹变化、时间nullable不一致、默认目录不兼容，修复后仅差量复测。
- 实网：显式 `YIKE_PUBLIC_AUTHOR_LIVE=1` 执行 `tests/integration/public-author-source-live.test.ts`，1 passed（3.99s），匿名固定索引及有界回复、无重试。日志未保留下实际返回数量，测试也允许空结果，因此不报告线索数或把它算正例验收，不为补日志重复请求。另一次固定主题1232232的匿名API核对确认回复中有作者“已结束，请求关闭此贴”；此核对只是来源证据，不是模型识别成功。
- 人工复核与发送门禁未改；无真实模型调用、Windows实机、客户UAT、构包、部署或外发。邀请候选仍fbf9f94，线上模式不变。完整Goal继续。

后续验收优先：真实项目原文及作者更新经过普通HTTP入库、实际模型判断与人工重开对照；包含“仍开放/补充限制/已关闭”不同样本。不重复用负例数量或合同通过数替代机会质量。作者专属变化事件和首页提醒仍待后续实现，本片仅保留版本及gaps。

### 独立审核修复

首次审核 `47416bd` 为NO-GO：P1保存时递归过滤null，导致旧必需字段与未知回复数量丢失；P2模型入参允许作者更新null。修复 `8d6e1c7` 仅保留旧六字段完整形状、存在时追加context，并严格要求作者更新各项为字符串。P1隔离PG先1失败后1通过（1.39s），增强当前/历史键集与nullable断言；P2直接入参测试先1失败后6通过（0.18s）。旧测试使用不匹配description可能因无关引用失败，本次改为直接测入参边界，避免假通过。未重复构包或全套测试。

非作者差量复审 `8d6e1c764f96436a5bd39b4071efc904b8688e6e` 为GO，两项关闭；只批准合main，不代表上线或完整监控。本批末次同步发现CodexWin已追加 `1119985/0b5bcbd/a56aab2`，包括Windows环境恢复和customer更新的实测记录；上方fbf9f94为本批启动时状态，最新发布状态以 `docs/qa/SERVER_137138_DEPLOYMENT.md` 与 `docs/qa/WINDOWS_SYNC_20260912.md` 为准。本批作者上下文代码仍未部署，Mac没有重复远程验收。
