# V02-01B 候选验证记录

2026-09-09。实施者 CodexiMac；基线为 01A 候选 `da2a2f233e716551289a833e623477f122aa230c`，main 基线 `15ddb7039e385c9adbda04bfd553bf8d222e6308`。

## 子项范围

[服务端会话撤销](../contracts/V02_SESSION_REVOCATION.md)。仅退出撤销、签名凭据唯一性和全部已有 HTTP 登录入口统一检查；正常手机号登录、激活、设备密钥绑定与平台执行未完成。

## RED → GREEN

- 初始真实数据库用例：退出后重建服务仍接受旧凭据；同秒凭据完全相同。2 failed。
- 畸形签名身份与同秒独立性：8 failed、5 passed；修复后 13 passed。
- 非规范签名尾位：先观察 1 failed、1 passed，收紧规范编码后完整纯凭据用例 15 passed。正常签名 padding 的等效字符串仍映射同一撤销键。
- 初步 PostgreSQL＋纯凭据检查 23 passed；后续补齐独立对抗矩阵后按下述完整定向组合复跑。

## 定向组合验证

专用本机 PostgreSQL 16；合成租户/账号；应用角色 NOSUPERUSER / NOBYPASSRLS。先由受信测试迁移完成 105，再由应用角色做业务操作。两个测试环境变量为 `YIKE_IDENTITY_TEST_DATABASE_URL` 和 `YIKE_IDENTITY_TEST_APP_DATABASE_URL`，不得指向生产库；具体凭据不进入交接材料。

```sh
uv run --frozen pytest -q tests/test_pilot_*.py tests/test_ui_api.py tests/test_identity_contract.py tests/test_session_auth.py tests/test_identity_postgres.py tests/test_session_revocation_postgres.py
uv run --frozen python -m compileall -q pilot tests
git diff --check
```

结果：**143 passed、2 skipped**；compileall 和 diff check 通过。2 个 skipped 是其他通用 PostgreSQL 环境变量未配置，不是本次专用身份/会话测试被跳过。

`baseline_regression_audit` 独立编写 27 项 PG 对抗测试，由实施者另行复跑；涵盖旧 token、混合 Bearer/Cookie、双租户/同租户不同人、重复退出、等效 padding、dev bridge、RLS、用户归属 FK、存储失败及双凭据事务回滚。正常流程为真实 PostgreSQL，数据库故障用显式故障注入；不证明真实平台账号或生产可用。

## 审核及主线门禁

`review_identity` 对 `adcb63193616403cc6072562098c7a7d5c7abd45` 独立复跑 143 passed、2 skipped，给出 REQUEST_CHANGES（0 Critical、1 Important）：新表权限未进入生产升级路径，且 FOR KEY SHARE 隐含要求用户表 UPDATE；原测试的全表授权掩盖了缺口。测试作者不是最终审核者，01A 的 PASS 不覆盖本次。

### 权限修复候选

- 新增受信 `deploy/grant_session_revocations.sql`，仅新表 SELECT/INSERT，目标为既有受限非 owner 应用角色；运行手册和部署入口明确迁移→最小授权→新版应用顺序，Web 不含管理员环境。
- 鉴权用户查找恢复只需 SELECT，撤销表复合 FK 保留用户归属保护，不向应用增加用户表写权限。
- 新增 `test_session_upgrade_postgres.py`：另建不继承 identity_app 的一次性受限角色，只授予旧用户表 SELECT；先复现升级脚本缺失、再复现 `permission denied for table pilot_users`，修复后验证最小权限下访问、交换、退出和拒绝旧凭据。没有对该角色做全表授权。
- 上述定向组合加 `tests/test_session_upgrade_postgres.py`：**147 passed、2 skipped**，compileall/diff check 通过；权限脚本重复执行和拒绝空/未知/特权角色均已覆盖。

修复候选待锁定新 SHA 复审。CodexWin 交叉验证尚未发生，未合并 main、未部署。

全仓仍有[历史测试基线漂移](BASELINE_TEST_DRIFT_20260909.md)，另在 `codex/mac-baseline-test-clock` 修复，不使用本子项定向通过宣称全仓 green。
