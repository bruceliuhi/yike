# 连接版本后端：Windows限定接收

日期：2026-09-09。接收基线`2ce6f8a8076765cdbb7122b08175cd2f01cf1abd`；连接后端、107迁移与原专项测试和Mac代码`a8a36fecba408e22a201ce6e3f14da2c0b30a857`字节一致。规范：[连接版本合同](../contracts/V02_CONNECTION_VERSIONS.md)；[Mac交接](../handoffs/V02-01C_CONNECTION_VERSIONS_MAC_TO_WIN.md)。

## 结论与范围

CodexWin限定ACK连接版本、后端操作回执及事务内当前态检查，不是完整01C或真实平台能力。独立`connection_cross_review`静态代码/架构及真实Windows质量复核PASS，无新增P1/P2。新增消费测试由另一非实现者`review_boundary_cases`审核PASS；主线产品代码未修改。

可供后续接入使用：严格请求绑定；同请求重放不重复变更；HTTP200可能REJECTED；历史SUCCEEDED不代表当前版本仍有效；同用户不同设备不能错绑；当前态检查使用调用方同一事务。仍须按合同完成持钥、任务、策略/预算、run/lease/generation的完整执行授权，不以连接回执替代。

## 本轮实际证据

| 检查 | 结果与边界 |
|---|---|
| 静态审核及纯测试 | 23 passed/0.15s；源码、迁移、grant、原PG覆盖逐项核对，不把静态PG覆盖计作运行 |
| 最终Windows PostgreSQL专项 | 68 passed、0 skipped、0 failures/errors，17.44s；纯23＋原PG40＋新增消费5 |
| 真实Windows往返 | Node24.19.0 → 本机loopback HTTP → PostgreSQL16.15非owner应用角色；错设备、200/REJECTED、同request错binding、旧版本拒绝、历史v1与当前v3分离均通过 |
| 隔离/权限 | 一次性tmpfs数据库、随机127.0.0.1端口；无super/BYPASSRLS/表owner，核对RLS及回执无UPDATE/DELETE；Node子进程不继承DB/管理员环境 |
| 清理 | 本次两轮随机命名容器均停止并确认移除，HTTP服务退出；没有访问客户库/真实平台，未停止其他容器或进程 |

新增文件`tests/test_connection_versions_win_boundary.py`，测试提交`d3e1bf0`，SHA256 `f946f7e2ae794e95b89866e01f7414ae36a157153b05bd56d9f33d97c827c1cf`。

最终原始XML（本机忽略目录）`.runtime/connection-win-d1f6c0ae4b7347dab068edf7e72310fc.xml`，SHA256 `a94480d55bf8ea202af5a469fe4cb9a9d5e861bbe669dcba0493b73a24ff182e`。复现脚本`.runtime/review-connection-win.ps1`，只为当前合成隔离环境；不会向产品包加入数据库凭据。

首轮66通过、2个新增HTTP夹具错误保留在`.runtime/connection-win-6ffc7338706b4eff9e2a8556bd878767.xml`；`Headers.update`错误使用关键字参数，仅改为mapping，独立复审后完整重跑得到上表结果。首轮Node24.11.1往返成功仅是非交付版本历史记录；最终使用项目受支持的24.19.0，不放宽Node预检。

## 明确保留的未完成项

- 现有desktop连接页面/IPC还未消费此接口；需按05D扩展原请求ledger、连接/设备/版本绑定和核对，不继续使用`disconnect(platform): Promise<void>`假包装。
- loopback受控开发HTTP不是生产HTTPS、Origin部署或安装包实机体验验收。
- 真实平台登录、来源读取、凭据隔离存储和完整执行授权尚未验收；合成CONNECTED只能证明后端判断逻辑。
- 未重复全仓、Windows打包或Mac1037/630集合，不把旧成绩相加；整个上线Goal仍ACTIVE。
