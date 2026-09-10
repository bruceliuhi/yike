# 任务结果进入复核

基线61fbfe6，已批准V0.2链路接续。复用任务feed与既有候选复核，不另建候选/任务模型。

## Global Constraints

- taskId 过滤只能选择当前认证 owner/tenant 可读取任务；不存在/非本用户任务404，不读取其他客户数据。
- 本任务发现过的候选使用 observations→batches.task_id 归属，不只检查最新 observation。返回仍为候选当前最新版本及现有复核状态，绝不将新版本冒充原任务原文。
- 去重候选数与采集入库记录数不同，页面解释清楚；读操作不评估、不采集、不发送。复核仍绑定原有版本/策略和人工确认。
- 过滤参数贯穿HTTP、客户端schema、请求和响应taskId关联核验；失败不能作为空列表。跨任务/账号切换清除选择、确认和晚到响应。
- 复用现有页面样式；仅定向测试、一批独立审核及一次前端构建，不复跑未变全套；本批不是Windows/真实平台/上线证据。

## Task 1: 后端按任务归属过滤（独立实现 Agent）

只改 pilot/candidate_review.py、pilot/candidate_review_api.py 和对应Python测试。当前 GET /api/ui/candidates 增加可选 taskId UUID。list_candidates增加 task_id=None；在既有listing snapshot内核对原execution task当前owner/tenant存在，不存在404 task_not_found；过滤通过相关EXISTS observations join batches (tenant_id,owner_user_id,platform_run_id,request_id)，关联 q.candidate_id 和 b.task_id。过滤在SQL发生，保持现有 MVCC/策略复核/分页语义。不引入迁移和新数据库。

返回现有page DTO，只有请求taskId时新增 `taskId:原查询UUID`。保持未过滤旧DTO字节字段不变。与ids/status/平台/文本交集，复用每候选当前projection；重复观察不重复计数，旧任务发现过但随后更新的候选仍出现最新版本。参数非法422；HTTP未知/重复字段仍拒绝。

定向实PG受限角色测试：两任务不混、同候选多次观察只一条、旧任务仍能看到后续最新版本、状态/ids交集、taskId回显、同tenant其他owner/跨tenant任务404、未知UUID404、非法/重复参数422。复用既有candidate review/ingestion fixture；仅新测试+相关API测试，不重跑全review suite。独立 cached postgres:16-alpine 容器，本批用后清理合成卷，不动共享PG。Python /tmp/yike-main-merge.PZkSlU/.venv/bin/python。报告放worktree git元数据sdd绝对目录，提交只自己文件。

## Task 2: 页面闭环（root）

Workbench已启动判断优先taskFeed.list(limit1)，读取失败保持待核验，不转用失败旧tasks；没有新服务的旧集成保留原路径。已有任务步骤跳转/collection。

共享candidateQuery和page解析加taskId及请求响应精确绑定；YikeService映射保留taskId。采集详情“查看本次发现线索”→/candidates?task=UUID；待判断页带任务标题/返回任务、说明当前最新版本与去重口径，所有读取保留taskId。默认显示全部状态方便回看已纳入候选，可自行筛选。当前任务参数与sample不可混用；切任务/账号重置作用域，已有候选deep link可以与task交集。

定向测试真实service路径与忽略/错误回显拒绝、首页已有任务/失败、UI按任务筛选/状态切换保留任务/切任务旧确认不提交。最后一次独立整批审核、renderer构建和正常main快进推送；完整goal继续。
