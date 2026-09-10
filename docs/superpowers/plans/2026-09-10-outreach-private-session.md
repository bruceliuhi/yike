# 07B 私有客户端派发链

基线2ff5cab，完整V0.2既有06/07范围，不增加产品菜单。沿用已确认的123协议和本机消费设计。按subagent-driven-development分工：独立agent实现严格请求/签名校验，根负责实际serviceClient、身份scope及消费会话接线；非作者整批审核一次。只做本批定向测试、一次typecheck，不构包或操作真实平台。

## Task 1: 私有派发协议与签名

仅新增desktop/src/main/outreachDispatchProtocol.ts、outreachDispatchSigner.ts及desktop/tests/outreachDispatchProtocol.test.ts。协议精确匹配pilot/outreach_dispatch.py：CLAIM/RESULT请求默认补齐resultId/outcome及outcome可选null，严格UUID/version/SHA/布尔/回执ID/时间。导出dispatchRequestSchema、DispatchRequest、validatedOutreachDispatchOperation，固定operation为outreach.dispatch.prepare/apply/receipt，payload分别为{request}、{request,signature}、{requestId}。路径对应123 signing-payload/dispatch和122 GET /api/ui/outreach/queue/{requestId}，所有未知/任意路径拒绝。

signOutreachDispatch({key,prepared,expected:{serviceOrigin,userId,tenantId,request}})验证服务返回{signing_payload}：独立protocol、user/tenant、非空64位session_digest、规范Python JSON、原request完整相等，key scope/Ed25519公私匹配；仅签原UTF8字节，返回{request,signature}。session_digest取已认证私有transport准备响应，不来自renderer；会话轮换由scope请求前后守卫负责。拒绝重复key/篡改请求/错域、敏感错误只固定码。复用已有密钥能力，不新增依赖或任意签名IPC。TDD后报告短证据，不自行push。

## Task 2: 已有传输接一次消费

根在serviceClient加入同队列/超时/容量/禁止redirect的私有requestOutreach；身份controller的worker scope只加入受原session epoch约束的该通道，公共API仍不开放派发。新增outreachDispatchSession：从身份scope读取原设备与vault key，原确认绑定进入CLAIM prepare/sign/apply→已有outreachConsumer→RESULT prepare/sign/apply。每次await后核验会话/取消；CLAIM只调用一次，不重试发送。RESULT提交或查询失败留UNKNOWN/RESULT_PENDING，不冒充已接受；允许只读查询原request恢复，不重新领取。没有有效首次grant不调用渠道。固定已审consumer/journal/channel由主进程装配，renderer不可注入。

本批不改Win main/IPC/UI，不新增实际平台driver；真实平台与客户端剩余集成仍是必做，不能称端到端完成。目标是使真实HTTP传输和现有组件形成可被Win消费的一条调用链，而非模拟消息发送成功。结果持久恢复及平台查询仍须后续实际通道完成；在此之前不开放外部发送入口。

## 本批验证

代码3478556。scope新增通道先RED（不存在方法），接线后55项受影响scope用例PASS。协议最小RED后18项定向PASS及Python固定字节向量见[协议短报告](2026-09-10-outreach-protocol-report.md)。根会话缺模块RED；首次接线3失败来自prepare裸request与{request}封装不一致，修复后HTTP会话4项+现有serviceClient6项合跑10 PASS，根tsc退出0。没有全量回归/构包。子agent另做了一次tsc，与根重复，后续已明确统一根执行以避免再重复。

HTTP测试实际使用localhost网络、现有serviceClient及真实Ed25519，但服务/平台响应是合成fixture，journal在本批HTTP测试为替身；真实文件防重证据复用上批，未声称本批已跑PG、真实平台、Windows或生产部署。

独立`private_dispatch_review`对3478556发现一项P1：scope身份失效没有即时传给execute内部等待中的driver，caller signal仍有效，可能注销后点击。审核用内存加载fixture只读复现，未改文件。修复必须让scope生命周期即时abort并组合传给driver，不能仅事后挡RESULT；已发生动作的晚回执仍保留。该问题未关闭前不合入。

修复`e2aa65f`由独立实现Agent完成，RED 5失败、修后两受影响文件61 PASS及typecheck/diffcheck通过，具体见[差量简报](2026-09-10-outreach-cancel-fix-report.md)；其余协议/传输字节复用原证据。`private_dispatch_review`差量复核后整批`2ff5cab..e2aa65f` GO，原P1关闭、无新增阻断，未另跑测试或构包。仅接收私有工程调用链；持久outbox、实际driver、main/IPC/UI和产品验收仍未完成。
