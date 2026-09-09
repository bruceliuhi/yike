# V02-01C 连接版本后端切片验收

日期：2026-09-09。实现者：connection_versions_implementation；集成与独立复跑：CodexiMac；独立任务源码审核：connection_version_review。

候选：`a8a36fecba408e22a201ce6e3f14da2c0b30a857`，计划基线 `94437cdb1fce605aaa85bd7a1025ee0702c392de`。工程主任务01C未完成；本文件不代表实际Win接收、真实平台、完整执行许可或上线。

## 交付

107迁移提供单调连接版本，显式重连即使vault引用不变也递增；断开/撤销使旧版本失效。新POST/GET连接操作使用严格请求、不可变历史回执、幂等冲突和所有者/客户空间隔离。受信旧管理接口保留语义，真实HTTP在写事务内重新核验会话；`lock_current`只在调用者事务内检查当前版本，不单独授予执行权。详细请求、错误、锁顺序及升级见[协议](../contracts/V02_CONNECTION_VERSIONS.md)。

未改101～106迁移、desktop、连接器或默认平台能力。REGISTER仍为UNVERIFIED；合成CONNECTED只用于测试失效检查，不是真实登录证据。

## 测试与独立审核

| 检查 | 结果及边界 |
|---|---|
| 实现者规定定向10文件 | 224 passed in33.55s，0跳过；新增23个DTO与40个PG用例 |
| 实现者补充断言 | 原始SQL溢出回滚1通过；回执查询等锁后过期反例先失败、恢复代码后1通过；不与全量相加 |
| CodexiMac完整后端 | `uv run --frozen pytest -q --tb=short`，1025 passed in82.47s，0跳过，exit0 |
| CodexiMac静态检查 | compileall pilot/tests、secret_scan及diff --check均exit0 |
| 独立任务审核 | 对精确a8a36fe规格合规、代码质量PASS，无Critical/Important/Minor待改项；审核者未冒充运行上述测试 |

完整后端运行时配置四个专用本地测试DSN：`YIKE_PILOT_ADMIN_DATABASE_URL`、`YIKE_PILOT_DATABASE_URL`、`YIKE_IDENTITY_TEST_DATABASE_URL`、`YIKE_IDENTITY_TEST_APP_DATABASE_URL`。本文件不记录凭据值。运行期间后端和测试字节冻结在a8a36fe，只有并行版本规划文档提交为4d974aa；非平台实测。

PG测试观察真实Lock wait_event后再释放，覆盖检查器与重连/断开/撤销双向竞争、相同及不同请求、注销先后、锁等待过期、原回执重放、插入失败整笔回滚。独立随机数据库101～106升级107两次及授权两次，验证受限角色、FORCE RLS、不可变回执与不安全授权拒绝。

## 明确边界与反例

- 不存在或他人设备也需持久拒绝，但不能外键指向他人的授权：requested_device_id与nullable authorized_device_id分开，后者为空只允许安全device_unavailable且连接结果全空。
- PostgreSQL原始INTEGER表达式可在触发器前溢出；支持的业务接口在锁内预检并给稳定耗尽错误，触发器可观察的MAX字段变化给YC001。两者原子回滚、不重置版本；没有为任意SQL表达式添加新类型或助手接口。
- 旧106升级测试使用“最后一条迁移之前”在新增107后失去105基线；改用明确迁移ID选择，保留原105状态断言，未删减身份安全测试。
- 回执查询后遗漏会话墙钟复核的敏感性用真实表锁测试验证，临时移除该复核时失败；恢复相同生产代码后通过。

## 后续接入门禁

remote9e27723的前端断开仍调用`disconnect(platform)`并期待void，只在本地保存UUID。05D须显式接入request/device/connection/version及GET原回执，不能将HTTP200的REJECTED当成已断开；当前默认不可用保持。检查器还须与持钥、任务/策略/预算、run/lease/generation和结果提交同事务衔接。完整01C、02B、03A、真实Windows、平台收发、生产及UAT继续未完成。

整分支、远端合并及最终验证另行追加；本候选测试不预先证明后来代码通过。
