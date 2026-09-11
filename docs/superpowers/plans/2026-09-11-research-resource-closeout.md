# 研究资源收口 Implementation Plan

> **For agentic workers:** 使用 executing-plans 执行这一有界任务；独立非作者审核后合入 main，不修改冻结候选。

**Goal:** 用户能区分资源记录齐全、在途和未知，不把许可计成实际消耗。

**Architecture:** 既有 PostgreSQL 事件的只读状态投影进入现有研究状态 API、严格 TS 合同与进度页面；无新数据库迁移。

**Tech Stack:** Python/psycopg、PostgreSQL、TypeScript/Zod、React。

## Global Constraints

- actualSoubei=null、settlementState=PENDING；没有收费/余额释放。
- 过期许可只观测，不转写 UNKNOWN；保留迟到回执。
- 不部署、不构包、不访问真实来源或短信。

## Task 1: 资源收口贯穿服务与页面

文件：pilot/research_runtime.py；desktop/src/shared/researchRuntime.ts；desktop/src/renderer/pages/tasks/ResearchProgress.tsx；tests/test_research_runtime_postgres.py；desktop/tests/researchRuntime.test.ts；desktop/tests/ui/research-progress.test.tsx。

- [x] 先追加失败断言：完成序列的 `usage.resourceCloseout` 包含 `state: 'RECORDED', overduePermits: 0, asOf`；旧代码缺字段应失败。
- [x] 在 _dto 的读取事务先设置 `REPEATABLE READ READ ONLY`；资源分组读取同时计数 `status='ISSUED' AND deadline_at<=asOf`，使用同一快照数据库时间。在已有阶段计算后按设计优先级派生状态，旧原始计数不改。只有 task/run 真正终态才可 RECORDED，协调器 STOPPED 不代替终态。
- [x] TS 增加可选严格对象及跨字段校验：overduePermits<=pending；RECORDED 必须终态且无 pending/unknown；UNCERTAIN 不允许继续动作；新字段缺失保留旧服务兼容。
- [x] 页面展示四种状态、快照时间、超期数及许可/结果计数；缺字段明确服务尚未提供，不声称已结算。仅 asOf 更新不算新进度，不能导致继续循环推进。
- [x] PostgreSQL 添加取消+在途+迟到finish、过期只读、UNKNOWN及租约断言；UI覆盖新状态与旧服务。执行 `pytest -q tests/test_research_runtime_postgres.py tests/test_research_runtime_fence_postgres.py`（专用PG），`vitest run tests/researchRuntime.test.ts tests/ui/research-progress.test.tsx tests/researchRuntimeClient.test.ts` 及 tsc，不跑全套或构包。
- [x] 独立非作者对固定 diff 审核，修复真实问题后定向复验；更新本记录与任务书，提交 main。完整 Goal 保持 ACTIVE。

## Evidence

2026-09-11 实现候选 `ed74a0f`，尚未部署/构包：

- `_dto` 使用单次 `REPEATABLE READ READ ONLY`；首个读取取得数据库 asOf，再读取任务/run/协调器/资源分组。过期许可仍为 ISSUED，不写回状态；外部分析读取只能保守阻止收齐。
- task/run 均终态且无在途/未知/有效租约才 RECORDED；STOPPED 协调器但任务非终态保持 OPEN。客户端严格校验计数与状态；旧服务缺字段明确未提供，实际搜贝保持 null/PENDING。
- 后端先 RED `KeyError: resourceCloseout`，扩展断言 6 failed / 5 passed；最终真实隔离 PG 的 `tests/test_research_runtime_postgres.py tests/test_research_runtime_fence_postgres.py` 为 **11 passed / 26.18秒**。覆盖完成、取消在途/迟到结果、过期查询不改事件、UNKNOWN、有效租约、STOPPED非终态、跨身份和 RR/RO。过期记录由管理员合成历史行，不修改生产trigger或绕过运行权限；不是实际外部调用证据。
- 桌面先 RED 7 failed / 7 passed；最终 `tests/researchRuntime.test.ts tests/ui/research-progress.test.tsx tests/researchRuntimeClient.test.ts` **16 passed / 2.53秒**，TypeScript 通过。新增快照时间导致原进度比较恒不相等的问题已修正，只忽略 asOf，验证没有进度变化时只推进一次。
- 非作者 `platform_query_full_review` 对 `d6da8a3..ed74a0f4faa007a6ed9aa8e21a7ecdb386a6ea39` 整批 spec/quality 审核 GO，无阻塞 P1/P2。后续仅证据文档，不改变产品字节。
- 没有全量测试、构包、生产/平台/短信操作；当前线上/邀请包仍固定 fbf9f94。完整 Goal 不因此完成，实际计量规则、财务结算、更多来源、Windows 与跨行业客户验收仍待推进。
