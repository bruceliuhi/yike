# 原子研究启动与资源预留

基线：`3c2f473`；在用户已授权 V0.2 内自主细化。前置为已确认策略和只读签名 quote。本批不批准价格、不扣账户余额、不装配未完成的研究 worker、不开放普通页面研究启动。资源预留是单任务上限锁定，不是充值余额扣减或已发生消耗。

## Global Constraints

- 已签名 `ExecutionOperation` 的字节、旧请求摘要和普通执行回执保持兼容。quote 令牌仅作为新入口外层信封中的 `authorization_token`，不得入库、日志或客户端恢复账本。
- 身份、当前画像/策略/来源、设备签名、平台集合、quote 规则及有效期均由服务端核验。研究目标必须恰好覆盖已确认策略平台，不能以子集偷偷缩小研究范围。
- 预留与任务/run/platform/START 回执在同一数据库事务内提交；失败全回滚。同请求同输入恢复同一结果；同请求换 quote、同 quote 换请求均拒绝，不重复创建。
- 旧执行 START 不得绕过研究预留。普通 CLAIM/RENEW/FINISH 和候选上传不能把研究任务当无计量普通采集运行；本批在真正研究 worker 接入前保持拒绝，CANCEL 和历史读取保留。
- 默认运行时仍不装配研究组件；没有显式规则及能力不返回可用/假数字。合成能力和数据仅证明事务合同，不代表真实采集、模型消耗或上线。
- 受限 PostgreSQL 强制租户/用户 RLS；最小授权；无生产连接。只运行定向测试，整批一次独立代码审核，文档不重复构包。

### Task 1: 服务端原子启动与恢复

在 `pilot/research_execution.py`、`pilot/research_execution_api.py` 实现研究专用服务及入口，最小修改 `execution_runtime.py`、UI 注册与 web 装配参数。新增下一编号迁移及对应 runtime grant。代码执行处复用已有 request advisory lock、设备签名、策略解析和事务，不另开写事务，不复制完整 apply/_start。

服务接口可自定内部细节，但 HTTP 固定为：

- POST `/api/ui/research-execution/start`：严格 JSON 信封 `{request: ExecutionOperation(START only), signature: canonical device signature, authorization_token: string<=8192}`；32KiB 限制、无 query、HTTPS/Origin/真实 session、no-store。错误只返回固定 code，不输出令牌或异常文本。
- GET `/api/ui/research-execution/operations/{request_id}`：历史恢复，不需要 quote 令牌、不重发、不刷新资格；只读当前认证用户原请求。没有研究回执返回 `request_not_found` 404，不把普通 START 伪装成研究 START。
- 成功响应严格对象 `{schema_version:'research-execution-v1', execution: 旧版 START 回执, reservation: {reservation_id, quote_id, strategy_version_id, profile_version_id, configuration_sha256, rule_version, rule_sha256, estimated_soubei, max_soubei, limits:{sources,minutes,modelCalls}, status:'RESERVED'}}`。UUID/SHA 与估算对应，正整数规则沿用已确认策略；estimated<=max。不返回令牌。状态只表示预留，非消费/结算。

建议 runtime 增加私有的同事务 research 钩子和专用 apply 入口，在原 apply 的 request 锁后做历史类型及 quote fingerprint 核验；旧 apply 的研究历史 START 不可当普通新受理。新专用服务验证令牌及 quote 数据与当前 strategy/profile/hash、tenant/user、draft/revision/max/limits/rule 完全绑定，并在锁定已确认策略后重验能力。使用数据库时间校验短 TTL。持久化不可变非秘密 quote 摘要、唯一 quote_id、request_id、task/run 复合外键及资源上限；绝不保存 authorization_token。

实现以现有事务入口为中心：预留行可在任务插入后、回执提交前插入，唯一约束/异常触发完整回滚；锁顺序保持原 session -> request -> device -> profile/strategy -> task 的顺序。新增研究 reservation 映射确保并发消费同 quote 只有一个完整任务。最终会话检查失败也必须回滚。

历史重复受理需要先认证、比较持久化非秘密 quote 摘要或令牌 SHA256（不是原令牌）；同请求同 token 在过期/策略撤销后可恢复历史，不能授权新动作。专用 GET 更适合丢失 token 的恢复。原普通 request fingerprint 不改写。

在普通执行及候选上传授权入口阻止研究 CLAIM/RENEW/FINISH/上传；显式报 `capability_unavailable` 或固定研究专用错误，不能只信当前 capability 回调。取消正常结束执行状态但本批不假释放预算；资源事实和安全释放留给后续结算。

TDD：先补失败测试，再实现。定向 HTTP 测试覆盖认证/类型/未知字段/大小/503/秘密不回显。受限真 PG 覆盖成功全表绑定、重复请求/quote 并发、失败回滚、策略及来源撤销、到期/规则变化、跨用户/租户、旧入口拒绝、普通执行仍可用、研究普通 CLAIM/上传拒绝、历史恢复。复用既有 fixture，专用临时 PG，勿操作共享数据库。只提交本任务所属文件，由 root 串行 commit/push。

### Task 2: 客户端私有传输合同

root 与 Task 1 并行：在 shared 新建研究 START 信封及响应严格 schema，复用现有执行签名与回执解析，校验 START、目标顺序/唯一性、quote/strategy/profile/hash/rule/数值上限绑定。只在 main 的 `executionServicePolicy.ts` 增加 `researchExecution.start` 和 `researchExecution.receipt` 固定映射，不向 renderer 公共 requestApi 开放签名/令牌能力，不改旧执行日志/签名协议。当前 TaskWizard/controller 的研究不可用保护不删除。

先 RED 后实现。定向测试覆盖合法新合同、所有关键错绑、额外字段/控制字符/错误数量、未知 schema、固定 URL 路由、公共 IPC 拒绝；运行相关测试与 tsc。此片是下轮安全研究 session/worker 的传输基础，不写成用户已能启动研究。

### Task 3: 合并验收与后续

串行审阅工作区、一次独立非作者审核整批实际 diff；修复重要问题仅追加相关定向测试。记录精确版本和剩余研究 worker/事件/结算/页面启动/真实 UAT 缺口，更新任务书及研究设计；同步远端，非破坏性合并并推送 main，核验 SHA 与 0/0。全量 V0.2 goal 保持 active。

## 实施证据

- 客户端 `94e0d68`、数值边界修正 `77ddbf1`：仅 main 私有传输和无秘密回执绑定；公共 IPC、旧签名/日志及研究启动保护不变。先两项合法路由 RED、再一项回执 RED；首轮五文件280通过+tsc，追加多平台和正数边界后仅两文件差量43通过+tsc（不与前者重复累加）。
- 后台 `de93521`：133迁移与最小授权、研究专用入口、同一执行事务写资源预留/任务/回执；只保存授权令牌SHA256，不保存令牌。估算请求UUID和START请求UUID独立。普通任务不需装配研究组件，研究的普通CLAIM/上传继续拒绝。
- 首次独立审核 `3c2f473..de93521` 为 NO-GO：两个P2是新START撤销/跨身份边界与新HTTP认证/503覆盖不足，不能用旧quote测试代替。`a18aa9a`补齐并由同一非作者差量复审关闭，有限GO仅覆盖本批原子START/私有传输。集成另复现普通策略`research=None`误带合法研究quote产生500，先RED再修为固定409并全回滚。
- 原后台新API+受限PG12通过；修复后只重跑两个新文件，24通过（代替原12，不重复累加）。新用例经实际web注册检查认证/HTTPS/Origin/503，经受限PG检查估算后来源撤销、跨用户/租户、重复quote、普通入口及取消/恢复。旧execution/quote限定回归98通过；UI/runtime/grant53通过、2项需真实DB先跳过，随后在专用PG启用空库授权测试2通过；没有重复大组回归或构包。数据、报价规则与能力注入均为合成测试；PG事务及受限角色是真实运行，不代表真实平台或模型已执行。
- 本批没有生产定价、扣费/余额、真实资源事件、研究worker、结算释放、客户端研究session/启动接线、构包、生产部署或真实平台/跨行业UAT。下一片接预算许可和可信资源事件，再接安全恢复与实际worker，不能只删除客户端保护。
