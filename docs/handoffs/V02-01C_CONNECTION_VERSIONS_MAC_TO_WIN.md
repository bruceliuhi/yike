# 连接版本后端切片：Mac → Win

日期：2026-09-09。候选 `a8a36fecba408e22a201ce6e3f14da2c0b30a857`；[协议](../contracts/V02_CONNECTION_VERSIONS.md)、[验收](../qa/V02-01C_CONNECTION_VERSIONS_REVIEW.md)。本文件不是实际Win ACK，完整01C仍未完成。

1. 服务端按运行手册升级107并授予新回执表最小权限；客户端不得获取DB或管理员凭据。
2. 新连接操作的所有字段都必须传递；REGISTER预期0只用于不存在自然键，重连带当前版本；DISCONNECT带具体连接ID和精确版本。
3. 每次逻辑操作保存同一个request_id和原绑定。超时查询原GET回执；404不是已失败证明，不盲目换新ID。历史SUCCEEDED是原操作结果，不能覆盖后来连接状态。
4. HTTP200可能为REJECTED；必须检查state、error_code及完整绑定。原评论/私信等发送确认不能借用连接回执作为执行许可。
5. 远端9e27723前端`disconnect(platform): Promise<void>`不能直接包装此API。05D需扩展原请求ledger、请求参数和恢复查询；登记、连接核验、已登录和可执行分别表示。现有默认不可用状态不能提前切换。
6. 真实Windows往返、设备私钥/会话存储和平台连接核验仍按各自卡验收，记录精确SHA、环境、通过/失败/跳过及实际接收时间。Mac1025项回归不替代Win复现。

03A/04A/B还须提供真实已确认画像、策略与预算和版本化配置，再衔接01C动作证明/租约及02B原子上传；不要用随机策略ID、伪CONNECTED或空运行记录绕过这些依赖。
