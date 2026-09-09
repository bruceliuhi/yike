# V02-01：CodexiMac → CodexWin 交接

更新：2026-09-09。本文件是交接操作说明与证据索引，实际接收状态仅记在[唯一实施任务书](../V02_IMPLEMENTATION_TASKBOOK.md#在途子卡与接收登记)；当前未收到 CodexWin ACK，不是接口依赖已就绪或功能已上线的证明。

## 候选与范围

- 服务端分支：`codex/mac-identity-execution-contract`；从 `15ddb70` 开始，已整合主干 `30da93e` 的全行业目标与 R3 交互。
- 01A：`da2a2f2` 设备/连接登记、报告事件，本地独立复审 PASS。
- 01B：`120b938` 服务端会话撤销，本地独立复审 PASS。
- 组合候选 `2f0626c` 合入测试时钟修复后，整合复核发现 104 三张新表的应用角色授权遗漏，结论 `REQUEST_CHANGES`。修复后锁定接收版本 **`222119e0b41b86b65867a92e14d3ed00dede4e7d`**，本机独立复审 PASS，根代理全量串行复跑 **705 passed、0 skipped**。失败、修复及验证边界见[组合验收记录](../qa/IDENTITY_INTEGRATION_20260909.md)。
- 该代码版本包含 main `30da93e`；main 后续至 `022b0fb` 的细化任务卡已由本交接文档保留，不把后来的文档提交冒充代码测试基线。
- **代码已在 `5d3373d9b7fa6cb74f0a9f6241bbb282e4db2514` 合入远端 main**，本机独立整合复审 PASS；该版本重新运行 705 项后端与 362 项桌面测试、typecheck/build 全部通过。代码集成不是实际 Win 接收，不开启手机号登录、平台连接或执行 capability。

## 接口与限制

契约已进入 main：`docs/contracts/V02_IDENTITY_REGISTRY.md`、`docs/contracts/V02_SESSION_REVOCATION.md`。接收时锁定下述精确集成 SHA；后续纯文档提交不改变该代码验证版本。

| 能力 | 当前含义 | 不能推导为 |
|---|---|---|
| `/api/ui/devices` 登记/列表、`/{id}/revoke` | 设备元数据与撤销 | 设备私钥证明或真实 Windows 绑定 |
| `/api/ui/connections` 登记/列表、`/{id}/disconnect` | UNVERIFIED 元数据；受租户约束的断开 | 已扫码、已验证账号、可采集或可发送 |
| `/api/ui/execution-events` | 限定字段的报告遥测；要求有效设备/核验连接 | 权威任务完成、游标推进或业务成功计数 |
| `DELETE /api/ui/session` | PostgreSQL 撤销已验证 Bearer/Cookie 后确认退出 | 自动撤销其他独立会话或已鉴权在途任务 |

租户由服务端身份解析，客户端不能自报 tenant、reviewer 或成功指标。错误使用既有 JSON 错误码，不返回底层异常或凭据。数据库失败不能授权，退出提交失败不能显示服务端已注销。重复退出幂等；平台报告事件暂非执行授权协议。

## 接收步骤

1. `git fetch origin`，在干净隔离审查工作区锁定 `5d3373d9b7fa6cb74f0a9f6241bbb282e4db2514`，保留其他任务的修改；其业务/测试代码与 `222119e` 完全一致，只正常合并了最新主线文档。不要只按移动中的分支头验收。
2. 阅读上述契约、`docs/qa/V02-01A_REVIEW.md`、`V02-01B_REVIEW.md` 和组合复审记录，确认客户端可正确呈现字段、状态与限制。
3. 准备专用一次性 PostgreSQL，管理员/应用角色分离，不与其他 reviewer 共用正在运行 DDL/授权测试的库。未发布的 104 旧候选 checksum 不得覆盖；新空库按候选运行手册执行迁移，再运行 `deploy/grant_session_revocations.sql` 对四张身份表的最小权限升级，最后启动应用。真实数据库凭据不提交 Git。
4. 设置专用测试环境变量 `YIKE_IDENTITY_TEST_DATABASE_URL`、`YIKE_IDENTITY_TEST_APP_DATABASE_URL`，执行 `uv sync --frozen --extra dev`，再运行 `uv run --frozen pytest -q tests/test_identity_contract.py tests/test_identity_postgres.py tests/test_session_auth.py tests/test_session_revocation_postgres.py tests/test_session_upgrade_postgres.py tests/test_ui_api.py tests/test_pilot_web.py`。skip 不算数据库验收通过；重点复现权限升级、租户隔离、旧 token 撤销、注销错误与不伪造连接。
5. 在唯一实施任务书对应子卡填写接收 SHA、日期/环境、复现命令与结果、`ACK` 或 `RETURNED` 及问题，详细输出可另建 QA 附件。只接受具体版本，不填写笼统“已看过”。

本机独立 Agent 不替代该签收；不假定两端共享对话或自动唤醒。无依赖的适配器/Windows 工作可继续，依赖接口在明确 ACK 前保持未就绪。

## 继续开发

按 main 最新小卡，CodexiMac 后续依次推进 **V02-01C 设备认证/执行授权**、**V02-01D 正常手机号登录/激活**；本交接不自动把未认领卡记为开工。P01 保持手机号＋验证码＋可选试用码，不改成密码登录或要求客户用 CLI 取 token。短信供应商、签名/模板、生产凭据与真实手机尚未验收，不能打开 sms_login。验证码明文不能进入业务数据库或日志；身份映射、一次性消费、限流、恢复和客户端白名单按契约继续开发。

设备认证需另行证明持有绑定密钥、服务端校验授权版本，并在撤销后拒绝旧权限。当前 ACTIVE 登记不能冒充该项。01、02、03 的整体完成标准保持不变。
