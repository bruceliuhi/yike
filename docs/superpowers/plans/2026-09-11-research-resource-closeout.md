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

- [ ] 先追加失败断言：完成序列的 `usage.resourceCloseout` 包含 `state: 'RECORDED', overduePermits: 0, asOf`；旧代码缺字段应失败。
- [ ] 在 _dto 的读取事务先设置 `REPEATABLE READ READ ONLY`；资源分组读取同时计数 `status='ISSUED' AND deadline_at<=asOf`，使用同一快照数据库时间。在已有阶段计算后按设计优先级派生状态，旧原始计数不改。只有 task/run 真正终态才可 RECORDED，协调器 STOPPED 不代替终态。
- [ ] TS 增加可选严格对象及跨字段校验：overduePermits<=pending；RECORDED 必须终态且无 pending/unknown；UNCERTAIN 不允许继续动作；新字段缺失保留旧服务兼容。
- [ ] 页面展示四种状态、快照时间、超期数及许可/结果计数；缺字段明确服务尚未提供，不声称已结算。仅 asOf 更新不算新进度，不能导致继续循环推进。
- [ ] PostgreSQL 添加取消+在途+迟到finish、过期只读、UNKNOWN及租约断言；UI覆盖新状态与旧服务。执行 `pytest -q tests/test_research_runtime_postgres.py tests/test_research_runtime_fence_postgres.py`（专用PG），`vitest run tests/researchRuntime.test.ts tests/ui/research-progress.test.tsx tests/researchRuntimeClient.test.ts` 及 tsc，不跑全套或构包。
- [ ] 独立非作者对固定 diff 审核，修复真实问题后定向复验；更新本记录与任务书，提交 main。完整 Goal 保持 ACTIVE。

## Evidence

本节在实现后登记实际结果，不提前声明完成。
