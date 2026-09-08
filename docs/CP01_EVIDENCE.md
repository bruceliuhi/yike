# CP-01 / CP-02 当前运行证据

环境：独立临时容器 `yike-customer-pilot-pg`，PostgreSQL 15 Alpine，端口 55432；不使用现有其他产品容器。

命令：

```bash
YIKE_PILOT_DATABASE_URL='postgresql://pilot:pilot@127.0.0.1:55432/pilot' \
  uv run pytest -q tests/test_pilot_contracts.py
```

结果：CP-01/02/03 数据层与研究导入测试通过；最新完整命令（含四页 Web 与导入门禁）为 `9 passed in 0.76s`（含真实 PostgreSQL 集成测试；集成测试创建一次性非超级用户 `pilot_app`，验证 RLS 过滤与旧约束升级）。

另外执行：

```bash
uv run python -m compileall -q pilot
```

结果：退出码 0。

范围边界：这只证明 CP-01/CP-02 的本地数据层契约，不证明四页浏览器流程、真实平台采集、部署 HTTPS、备份恢复、真实用户试用或收入。

代码备份：Gitee `codex/customer-pilot` 分支，最新提交 `518417d5898bd9655dbd42d5d207793d0036f3ec`。该分支尚未部署。
