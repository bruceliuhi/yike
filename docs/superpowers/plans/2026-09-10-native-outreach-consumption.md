# 07B 本机一次消费

基线945225f；按已批准任务07B执行/TDD，根实现新的主进程消费控制器，独立agent只实现新的消费日志，两者不改Win现有main/IPC/控制器。独立整批审核后统一提交。仅新增组件，不谎称客户端已接线。

成功条件：可信私有transport带回123首次grant后，控制器严格核验已确认上下文/owner/tenant/device/request/claim/摘要/来源URL及截止时间；只读本机核验原账号、收件人、渠道和连接版本；日志不可变且原子持久消费后，重验会话/取消/时间，再调用一次发送动作。重复响应、重复IPC、重启、写盘失败不能重新执行。结果只能是待提交的明确回执或UNKNOWN，不能伪装已被服务端接受。

文件：`desktop/src/main/outreachConsumptionJournal.ts`（设备保护加密、排他创建、fsync、失败关闭）、`outreachConsumer.ts`（验证和消费控制）、对应两个定向测试文件。复用锁定依赖，不新增包；新scope含serviceOrigin/userId/tenantId，跨session仍共享消费历史。记录仅请求身份和context摘要，不存正文/登录态。根不改agent负责文件。

通道接口必须由固定主进程适配器实现，不可从renderer注入；当前没有真实发送器，不把注入测试函数当平台能力。调用前渠道核验与期限复查，驱动仍须使用固定隔离profile并在动作点检查取消/账号。领取后任何不确定结果保持UNKNOWN，不自动解除防重。用户删除日志、所有操作系统断电保证及Windows实测不在本机测试证据中；不能把这些风险隐去。

先跑新增消费用例得到缺模块RED；实现后合跑两组定向测试及一次typecheck，不构包。必要失败仅差量补验。Win07C后续消费123签名grant和本机控制器、回传签名RESULT/回复，是端到端真实联验所需，完整Goal继续。
