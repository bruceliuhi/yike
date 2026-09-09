# main 集成差量核对

日期：2026-09-10。核对提交：`a31069fead15f395e7b4ec93c9c91e441beea798`。

**限定结论：PASS，可正常推送此集成提交。** 这是合并完整性和已审桌面范围保持不变的结论，不是对新远端后端作完整安全/业务验收，也不表示整个 Goal 完成。

## 实际检查

- 两个直接父提交为 `e70c3a1d048f0f3d6b13bf74805eb60ad4a587cf` 与 `ab6407d`；`git merge-base --is-ancestor` 分别成功，双方历史完整保留。
- `e70c3a1:desktop` 与 `a31069f:desktop` 的 Git tree ID 完全相同：`b620b42cbc70c16026258a2c36991d422ab10002`。桌面源码、测试、资源、构建脚本与包装文档均未被合并改变，上一轮架构 PASS 可继承；没有把源树一致等同于新包已重新构建。
- 相对已审 e70c3a1，远端增量为 33 个后端/部署/测试/文档文件，没有 desktop 变更。
- 扫描提交中的文本冲突标记未发现残留；任务书双边差异显示，远端 04C 候选复核、04B 真实确认策略、手机登录及其他执行记录得到保留，本地 05A 退出/画像/日程/连接读取记录也得到保留。05A、上层 V02/Goal 状态没有被自动标成完成。
- 新共享接线只增加可选 `candidate_review` 注入和其 router 注册，没有关闭既有 Origin、会话或认证要求；默认未注入服务仍保持 capability unavailable。更完整的新服务评估另列为后续合同接入工作。

上述核对使用固定提交对象，不依赖原工作树正在开发的新文件。没有修改源代码或运行会改变客户业务的操作，没有重跑未受合并影响的前端全量。

## 继承限制

先前报告 `/tmp/yike-ui-architecture-9999355.md` 保留原 NEEDS_FIX；其 registration P1 已由 `/tmp/yike-ui-architecture-e70c3a1.md` 绑定子提交关闭。P20 自作范围仍由另一代码审核者承担独立批准。

此集成检查不重新批准新后端的迁移、授权、并发与真实 PostgreSQL 行为；这些继续按远端独立交接报告及主线程接收验证执行。Windows 当前候选的安装/缩放/卸载、真实平台与客户数据、真实服务消费和完整状态视觉验收不能由本次合并推导为通过。

任务书中“额度限制、未提交”的 05A 段落属于此前本地证据时点；这次独立审核/集成进展应在主线程后续收尾记录中另行注明，不能回填旧包或旧测试的时点。

## 后续 P07 服务接入建议（只读合同评估，不是本次合并阻断）

以下依据此提交的 `docs/contracts/V02_CANDIDATE_REVIEW.md`、`pilot/candidate_review.py`、`pilot/candidate_review_contract.py`、`pilot/candidate_review_api.py` 以及现有前端候选模型/操作账本。当前前端默认复核服务仍未接通，因此本段属于启用真实新合同前的必要适配，不能只替换 HTTP 地址就宣称已兼容。

### 1. 先补完整回执，再把 sourceVerificationId 纳入新版确认哈希

服务端 INCLUDE 在 `pilot/candidate_review.py:270–275` 要求同绑定最新 OPEN 核验、24 小时内及真实声明的联系路径，并比对 `sourceVerificationId`。但成功 `receipt.review` 在 `:293–295` 仍只回旧七字段，遗漏该 ID；现有 `desktop/src/renderer/domain/candidateReviewOperation.ts` 的 schema/hash 和 `candidates.ts` 的 reviewSnapshot/sameReviewSnapshot 也只覆盖旧字段。

最小产物是版本化确认/回执合同：新 INCLUDE 的原确认快照与成功回执均保留核验 ID，哈希及回执匹配均包含它。不能把 ID 仅加在 POST 上、不纳入确认；也不能只升级客户端 hash、却让原 GET 回执没有对应字段。服务端不可变旧回执保留旧版本，新旧解析明确分支，不把缺 ID 的旧回执强制猜成最新核验。版本改变后旧本机账本仍可核对，不能清空或按新合同自动重发。

### 2. 分开建模分析、来源核验、人工复核三类原请求

现有 `Opportunities.tsx:1067–1104` 的 ASSESS 每次创建新 UUID，只接受 assessment 成功，pending/failure 被归为不匹配，缺少分析原请求的持久恢复。来源核验尚无独立前端操作。新后台的 GET request 则保留三类原操作响应、PROCESSING/UNKNOWN/failure，以及分析缓存别名 `invocationRequestId`。

建议保留原 decision 账本，追加带协议版本、operation kind、原 requestId 和完整绑定 hash 的最小记录；本机只存必要不透明 ID/hash，不落原文或凭证。先可靠落锁再调用，超时/5xx/取消等待保留原记录。查询是只读的 `GET /candidate-review-requests/{requestId}`，404/空列表不等于确定未执行。分析只有经原请求核对并符合服务端重试条件后，用户显式新建 requestId + retryOf；UNKNOWN 不自动退款、不显示 0 成本。alias 的 invocationRequestId 表示实际调用关联，不是另一次扣费或新提交许可。

### 3. 来源打开、人工核验和入库确认保持三步事实边界

`openExternal` 成功仅表示发起打开，不自动生成 OPEN 或人审核验 ID。应提供独立的打开方式、实际来源状态、逐字摘录/定位和联系路径确认，提交后严格比对候选 revision、sourceVersionId、画像版本及原 requestId 的 sourceVerification 回执。UI 不能填 checkedBy/checkedAt；这些由认证服务生成。

INCLUDE 仅引用该有效回执；候选/画像/来源版本变化、更新核验、超时失效或 BLOCKED/EXPIRED 时使旧确认失效。来源 OPEN 是用户声明，不是购买人身份核验或发送授权。当前 `publishedAt` 空字符串须显示未知，不补造时间；人工核验不刷新原发布时间。服务端 60 天限制及其他条件拒绝时，应保留输入并展示原因。

### 4. 历史核对只关闭原操作，不恢复新版本权限

现有 `Opportunities.tsx:1297–1354` 通过 `ids + reviewRequestId + page=1&pageSize=1` 核对 decision。新服务该路径返回保存的成功旧候选快照，另外标记 historical/currentBindingValid/assessmentStale；它不提供分析或核验的完整状态查询替代物。

客户端应严格校对 requestId、action、候选、完整确认 hash 后关闭对应原锁。历史快照可以展示“原请求已保存”，随后独立刷新当前候选；不能把它作为当前可复核/可发送的数据回灌。换服务/身份/可信账户空间、画像/来源 revision 或离页后，迟到响应只能处理原授权范围的原记录，不能覆盖新页面或新空间的输入。

### 5. 传输与最小接入顺序

固定 IPC operation 分别覆盖候选列表、分析/复核写入、人工来源核验和原请求查询；payload 不传 tenant/owner/reviewer/time。适配器要省略空 query（现 UI 传 `query.trim()`，服务端拒绝显式空 query）、转换为正式平台标识、验证 UUID 与所有新增状态；不能在 decoder 中剥离 sourceVerification 或历史/版本字段。

建议先交付只读真实候选/原文/历史状态，再补三个原请求查询与兼容账本，然后接单独人审来源核验，最后开启带新版完整确认快照的 INCLUDE/EXCLUDE。最少验收包括：成功回执丢失后精确恢复、同 ID 不同核验快照冲突、旧 OPEN 被新 BLOCKED 覆盖、同用户换空间晚到、旧账本不被清除、历史成功不恢复当前操作，以及样例/未知发布时间不能入库。上述是接入建议，未修改或验证新后端实现，也不触真实模型、平台或外发。
