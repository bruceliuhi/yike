# 07B 人工确认持久队列

基线`82ece97`，Mac继续既定07B，不改Win客户端。按触达合同实现真实PostgreSQL队列，不将队列接受说成平台已发送；本批不执行外部消息。

## 本批闭环

普通runtime新增签名字节准备、确认入队、原UUID查询和派发前取消接口。请求绑定上一批完整context摘要、原草稿、设备/连接版本、近期客户端渠道核验报告和明确humanConfirmed。签名沿用已登记Ed25519设备密钥，使用独立协议域及当前会话；签名字节准备不等于人工确认或发送许可。CONNECTED不能代替渠道核验报告；客户端报告只证明已授权设备的声明，不声称服务器实测平台。

确认事务重读同一cursor上的联系context，校验最新稿/画像/原文/账号/目标/版本和渠道报告时效。原UUID相同请求重放返回原历史；不同绑定拒绝。owner/商机/用途未决请求唯一，多窗口/换UUID/换账号不能重复入队。返回QUEUED、保存不可变上下文，不返回SENT。查询无执行副作用，404不是未送达。仅尚未派发的QUEUED可取消；取消结果可原键恢复，不自动重新提交。

迁移122归本片：`pilot_outreach_queue`强制tenant/owner RLS，内容不可改，状态仅允许QUEUED→CANCELLED；这不是完整派发状态机。后续06B原生渠道实际核验/单次派发、07B领取/未知对账与08回复关联仍须完成。未安装执行器时只有等待队列，不开全局outreach能力，不提供自动派发开关。

## 执行与验收

1. 写`tests/test_outreach_queue_http_postgres.py`，普通runtime实际HTTP先取得缺路由RED。
2. `pilot/outreach_queue.py`、`pilot/outreach_queue_api.py`实现上述事务/API；`ContactDraftStore.context_in_transaction`复用既有事实核验，同一事务完成入队，锁顺序统一owner→device/connection→profile。装配/122/最小授权同时接入。
3. 只测本批HTTP/受限PG、Ed25519、原UUID重放、跨会话/跨租户、换稿/旧核验/并发防重及取消恢复，回归受改context。一次独立整批审核、修复只测差量，提交main，不构包或对外发送。

## 本批验证

源码`8461892`；非作者`draft_batch_review`对`82ece97..8461892`规格/代码/事务/权限审核GO，无阻断，不重复测试或构包。签名和HTTP/PG均真实执行，但平台来源、连接与渠道观察为合成输入，**没有平台发送证据**。

- RED：首个实际HTTP缺`signing-payload`返回404（1 failed），随后实现。
- 根实际运行`tests/test_outreach_queue_http_postgres.py`当时9项及受改`tests/test_outreach_context_http_postgres.py`14项：**23 passed，9.92s，0 skipped**。
- 追加两项：数据库内容/取消状态不可篡改通过；新稿验证测试先因夹具沿用旧version=2出现409（1 failed/1 passed），改为old.version+1后仅该项重跑**1 passed，1.50s**。这是测试构造修正，无生产改动。最终覆盖11项queue和14项context，不冒称做过最终全量重跑。
- 均用隔离临时数据库及真实受限role；测试完成仅删除本次创建的数据库。没有输出/记录数据库密码，也未触碰生产环境。未改草稿CAS等证据复用前批，未做构包。

API和Win接法集中于[触达合同](../../contracts/V02_OUTREACH_CHANNELS.md#07b-人工确认队列2026-09-10)，122及授权见[部署说明](../../../deploy/README.md)。Win尚未ACK；不能将本批QUEUED/CANCELLED伪装成现有SENT/FAILED回执。后续真实渠道/领取/对账与回复原请求关联、客户验收均未完成，父卡和Goal保持进行中。
