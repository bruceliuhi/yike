# 已声明来源的定时执行修复计划

> 使用 executing-plans/TDD 执行，固定提交后一次独立审核。用户已授权完整V0.2内自主细化，不新增平台或外部动作。

**Goal:** 让已明确启用的新监控policy真正允许其声明的PUBLIC_WEB/知乎平台进入原有定时预约与签名START，不再被旧平台名单误拒绝。

**Architecture:** 保持support与capability_check；只补`MonitorRuntime.pulse`遗漏的project/bili_links两种已部署policy，继承四平台与固定公开来源，不改变旧三平台或once-only模式。复用原租约、设备身份、确认策略与日程，不重做调度器。

**Tech Stack:** Python、PostgreSQL、既有受限角色fixture。

## Global Constraints

- 基线main `aba38eb798f9b4e305a92fd958874ebc47a20fc8`，本任务独占worktree `/tmp/yike-v02-scope.Pwf9Fs`，分支`codex/monitor-author-updates`；不部署/构包/真实模型/平台/外发。
- 已知根因：support已识别`four_platform_public_project_monitor_policy`和`four_platform_public_bili_links_monitor_policy`，pulse的ZHIHU/PUBLIC_WEB名单未纳入它们。不得取消capability_check或让任意policy借新名单扩权。
- PUBLIC_WEB必须PUBLIC_ANONYMOUS且已确认固定source；知乎必须该客户设备的有效连接。首轮离线不补跑，只有当前monitor_session的到期轮次可预约；START仍签名并复核策略/会话。
- 这不是跨轮分页游标或作者变化通知完成；这些仍属完整V0.2后续执行项。本修复不新增UI合同或源码模式。

### Task 1: 已声明来源的真实PG预约/START

**Files:** 修改`pilot/monitor_runtime.py`；新增`tests/test_monitor_extended_sources_postgres.py`复用`tests/test_monitor_runtime_postgres.py`的runtime_databases/runtime_env/force_due_window/sign_apply。

- [x] 写RED：新两种policy下，确认PUBLIC_WEB三种固定来源、或ZH连接策略；先pulse建立本机会话，推进fixture日程为due，第二pulse返回READY，并签名START成功；原策略拒绝的来源仍拒绝。
- [x] 执行隔离PG定向测试，确认错误为`capability_unavailable`，不改fixture来规避。
- [x] 只将两种新policy加入pulse中ZHIHU和PUBLIC_WEB的policy集合；原连接/预算/预约/签名校验不动。
- [x] 重跑新测试、既有monitor运行合同/权限与能力policy定向覆盖，保留RED/GREEN，不做整仓测试。
- [ ] 固定SHA独立审核，补一处集中证据与任务书接续，正常合并推送main。测试数据库保留数据、停止自有容器；不影响其他worktree/运行实例。

## Evidence

新测试RED：`tests/test_monitor_extended_sources_postgres.py`，8 failed / 1 passed，7.08秒。两种policy×PUBLIC_WEB三source及ZHIHU均在pulse旧名单处`capability_unavailable`；旧node模式拒绝project来源的反例原已通过。

补齐pulse集合后，五文件定向组48 passed / 2 failed，17秒：新功能9项均通过，既有monitor CLAIM/RENEW两项失败因fixture未授予执行器已依赖的research reservation读取权限。正式`deploy/grant_runtime.sql`已有`grant_research_execution.sql`，因此仅把该实际授权脚本补入旧fixture，不修改生产ACL或删除研究判断。

最终命令（本任务独立loopback PG `yike_monitor_activation`，通过环境注入连接、不写入Git；Python `/tmp/yike-aliyun-sdk.DYc7GB/venv/bin/python`）：

```sh
python -m pytest -q --tb=short tests/test_monitor_extended_sources_postgres.py tests/test_monitor_runtime_postgres.py::test_real_pg_reserved_start_claim_and_pause_fence tests/test_monitor_runtime_postgres.py::test_real_pg_inflight_renew_holds_plan_share_lock_against_other_session_pause
```

11 passed，9.08秒。首次五文件组额外包含`tests/test_monitor_runtime_postgres.py tests/test_monitor_runtime_api.py tests/test_bili_link_collection_policy.py tests/test_public_node_collection.py`，不重复整组制造总数。实际数据库/受限角色/策略确认/到期预约/签名START已验证；平台采集、实际Windows和生产未执行。独立审核待固定提交。

## 下一批已核实的代码接点（不是已实现）

作者需求更新仍仅输出gap。独立只读调查确认：timeline V2/现客户端严格限定正文CONTENT，不能直接往V2加作者字段。下一批应显式`timelineSchemaVersion:3`协商，旧`{binding}`保留V2；V3在版本中保留作者ID与sourceContext，单列`authorChanges`（OBSERVED_NEW/MODIFIED、replyId、前后观察与逐字引用），前后同作者/同replyId才能断言修改；首次读到不等于刚发布，回复缺失/范围缩小不等于删除。复用留存candidate版本，不能从已丢replyId的冻结`author_updates[]`按下标猜。前后端严格验证与EvidenceTimeline/当日brief一并接通，再继续跨轮来源游标；不把此调查当成作者提醒完成。
