# V02-01A 审查与验证记录

2026-09-09，实施者 CodexiMac。只记录设备/连接登记及遥测候选，不表示完整身份登录或平台执行已完成。

## 首轮审查

`6b4316a`：独立 Agent `review_identity` 给出 REQUEST_CHANGES，未合并 main。

1. 执行 payload 可包含秘密别名与错误文本。
2. task_id 缺少同租户任务外键。
3. 设备/连接撤销与事件插入存在竞态。
4. 104 迁移重复注册。

## 修复验证

- 秘密别名/类型边界用例：先观察 8 failed，再改为按事件类型的窄字段白名单。
- PostgreSQL 测试：先观察 5 failed、1 passed，覆盖状态误报、任务/设备外键和真实撤销并发；修复后全部通过。
- 追加未核验连接的断开/设备撤销用例：先观察 2 failed，再修复。
- 组合验证：`test_identity_postgres.py test_identity_contract.py test_pilot_contracts.py test_ui_api.py test_pilot_web.py`，92 passed、2 skipped。其中真实专用 PostgreSQL 测试已运行，2 个 skipped 属于另外的通用集成环境变量未提供。
- API 中的 platform_connections 能力保持 false；用户登记只进入 UNVERIFIED，禁止用元数据登记冒充登录成功。

## 基线失败

全仓回归未通过。对基线 `15ddb7039e385c9adbda04bfd553bf8d222e6308` 的独立 git archive 运行 `test_bootstrap.py test_d04_remediation.py --maxfail=3`，复现两项历史权威断言与 `D04_FACT_OUTSIDE_RUN_WINDOW`，3 failed、3 passed 后停止。它们不是本候选新增文件引入，但仍是后续主线门禁修复事项，不能写成全仓通过。

## 复审状态

独立 Agent `review_identity` 已对 `da2a2f233e716551289a833e623477f122aa230c` 复审 PASS，范围仅为 V02-01A。审查者独立运行上述组合检查，92 passed、2 skipped，并核对行锁、复合外键、迁移唯一性、secret scan 与干净工作树。

CodexWin 实机/交叉验证尚未发生。本地辅助审查 Agent 不冒充 CodexWin，也不构成 Windows 验收。该提交未合并 main，V02-01 仍为 IN_PROGRESS。后续身份改动必须绑定新 SHA 重新审核，不能沿用本次 PASS。
