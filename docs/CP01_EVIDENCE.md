# CP-01 / CP-02 当前运行证据

环境：独立临时容器 `yike-customer-pilot-pg`，PostgreSQL 16 Alpine，端口 55442；不使用现有其他产品容器。

命令：

```bash
YIKE_PILOT_DATABASE_URL='postgresql://pilot:pilot@127.0.0.1:55442/pilot' \
  uv run --frozen pytest -q \
  tests/test_pilot_contracts.py tests/test_pilot_web.py \
  tests/test_research_import.py tests/test_pilot_import_cli.py \
  tests/test_pilot_provision_cli.py
```

结果：CP-01/02/03 数据层、任务租约、四页 Web（含来源状态、更新时间和匹配摘要）、失败任务提示、研究导入（含 60 天新鲜度与 URL 凭据净化）、受信 provisioning、日志脱敏、迁移职责、HTTPS 会话入口、代理头信任边界、同源状态同步和非法输入 fail-closed 测试通过；最新完整命令为 `30 passed in 1.44s`（含真实 PostgreSQL 集成测试；集成测试创建一次性非超级用户 `pilot_app`，验证 RLS 过滤与旧约束升级）。

另外执行：

```bash
uv run --frozen python -m compileall -q pilot tests
git diff --check
```

结果：两项命令均退出码 0。

另运行 `scripts/secret_scan.sh`，结果为 `secret-scan: clean`；该静态扫描不替代目标环境日志、备份和密钥管理验收。

范围边界：这只证明 CP-01/CP-02 的本地数据层契约，不证明四页浏览器流程、真实平台采集、部署 HTTPS、备份恢复、真实用户试用或收入。

代码备份：Gitee `codex/customer-pilot` 分支；当前远端提交 `a92c7fd`（完整回归覆盖至其前置代码提交），部署骨架已推送至 `2f8c439e5878cbada47b6354db52d0385279b3d6`。浏览器主流程记录见 `docs/BROWSER_ACCEPTANCE_CP04.md`；该分支尚未部署。
