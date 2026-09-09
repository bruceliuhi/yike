# 测试基线时钟修复：独立审核

2026-09-09。基线 `15ddb7039e385c9adbda04bfd553bf8d222e6308`，候选 `475166ac27e6d84ef019d669cc15cb9aec578ae4`，分支 `codex/mac-baseline-test-clock`。

实施 Agent `baseline_clock_fix`；独立只读审核 `baseline_regression_audit`；结论 **PASS**，无阻止集成的 P0/P1/P2 问题。两者不是远端 CodexWin；实际双机交叉验证不由本记录替代。

## 变更范围

候选只修改 11 个 tests/ 文件，生产 app/pilot/SQL 未改。历史测试用 opt-in、非 autouse 的统一时钟，保留可前进时间、原生 SQLite 日期解析与修饰符；标记 native_clock 的过期/回填反例完全退出时间替换。现行权威测试遵从 V0.2，同时保留历史草案原字节 hash。

## 绑定证据

实施者原样 RED：170 failed、431 passed、7 skipped、7 errors。

实施者修复后和独立审核分别运行完整测试：

```sh
uv run --frozen pytest -q -rs
# 实施者：624 passed、7 skipped
PYTHONDONTWRITEBYTECODE=1 uv run --frozen pytest -p no:cacheprovider -q -rs
# 独立审核：624 passed、7 skipped，34.93s
PYTHONDONTWRITEBYTECODE=1 uv run --frozen pytest -p no:cacheprovider -q -m native_clock tests/test_d04_remediation.py tests/test_web_contract.py tests/test_clock_fixture.py
# 独立审核：34 passed、126 deselected
```

独立审核另外按 clock fixture→pilot Web/UI 顺序执行，并逐例检查时间函数恢复、pilot 未启用 fixture：78 passed。工作树前后干净、HEAD 相同、diff check 通过。

7 项 skipped 是 test_import_atomicity 的 5 项及 test_pilot_contracts 的 2 项，缺少对应独立 PostgreSQL 环境变量；不能算作通过。本候选不含另一分支的 V02-01A/B 身份代码，两个分支的测试数量不可拼成一次整链验证。

候选未合并 main、未部署；不构成 Windows、真实平台、生产或客户试用通过。后续整合仍按唯一产品工作流及任务书执行。
