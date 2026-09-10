# 07B 私有客户端派发链

基线2ff5cab，完整V0.2既有06/07范围，不增加产品菜单。沿用已确认的123协议和本机消费设计。按subagent-driven-development分工：独立agent实现严格请求/签名校验，根负责实际serviceClient、身份scope及消费会话接线；非作者整批审核一次。只做本批定向测试、一次typecheck，不构包或操作真实平台。

## Task 1: 私有派发协议与签名

仅新增desktop/src/main/outreachDispatchProtocol.ts、outreachDispatchSigner.ts及desktop/tests/outreachDispatchProtocol.test.ts。协议精确匹配pilot/outreach_dispatch.py：CLAIM/RESULT请求默认补齐resultId/outcome及outcome可选null，严格UUID/version/SHA/布尔/回执ID/时间。导出dispatchRequestSchema、DispatchRequest、validatedOutreachDispatchOperation，固定operation为outreach.dispatch.prepare/apply/receipt，payload分别为{request}、{request,signature}、{requestId}。路径对应123 signing-payload/dispatch和122 GET /api/ui/outreach/queue/{requestId}，所有未知/任意路径拒绝。

signOutreachDispatch({key,prepared,expected:{serviceOrigin,userId,tenantId,request}})验证服务返回{signing_payload}：独立protocol、user/tenant、非空64位session_digest、规范Python JSON、原request完整相等，key scope/Ed25519公私匹配；仅签原UTF8字节，返回{request,signature}。session_digest取已认证私有transport准备响应，不来自renderer；会话轮换由scope请求前后守卫负责。拒绝重复key/篡改请求/错域、敏感错误只固定码。复用已有密钥能力，不新增依赖或任意签名IPC。TDD后报告短证据，不自行push。

## Task 2: 已有传输接一次消费

根在serviceClient加入同队列/超时/容量/禁止redirect的私有requestOutreach；身份controller的worker scope只加入受原session epoch约束的该通道，公共API仍不开放派发。新增outreachDispatchSession：从身份scope读取原设备与vault key，原确认绑定进入CLAIM prepare/sign/apply→已有outreachConsumer→RESULT prepare/sign/apply。每次await后核验会话/取消；CLAIM只调用一次，不重试发送。RESULT提交或查询失败留UNKNOWN/RESULT_PENDING，不冒充已接受；允许只读查询原request恢复，不重新领取。没有有效首次grant不调用渠道。固定已审consumer/journal/channel由主进程装配，renderer不可注入。

本批不改Win main/IPC/UI，不新增实际平台driver；真实平台与客户端剩余集成仍是必做，不能称端到端完成。目标是使真实HTTP传输和现有组件形成可被Win消费的一条调用链，而非模拟消息发送成功。结果持久恢复及平台查询仍须后续实际通道完成；在此之前不开放外部发送入口。
