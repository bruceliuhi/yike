# CP-01 / CP-02 当前运行证据

环境：独立临时容器 `yike-customer-pilot-pg`，PostgreSQL 15 Alpine，端口 55432；不使用现有其他产品容器。

命令：

```bash
YIKE_PILOT_DATABASE_URL='postgresql://pilot:pilot@127.0.0.1:55432/pilot' \
  uv run pytest -q tests/test_pilot_contracts.py
```

结果：CP-01/02/03 数据层、任务租约、四页 Web、来源状态、失败任务提示、研究导入和受信 provisioning 测试通过；最新完整命令为 `19 passed in 2.79s`（含真实 PostgreSQL 集成测试；集成测试创建一次性非超级用户 `pilot_app`，验证 RLS 过滤与旧约束升级）。

另外执行：

```bash
uv run --frozen python -m compileall -q pilot tests
git diff --check
```

结果：两项命令均退出码 0。

另运行 `scripts/secret_scan.sh`，结果为 `secret-scan: clean`；该静态扫描不替代目标环境日志、备份和密钥管理验收。

范围边界：这只证明 CP-01/CP-02 的本地数据层契约，不证明四页浏览器流程、真实平台采集、部署 HTTPS、备份恢复、真实用户试用或收入。

代码备份：Gitee `codex/customer-pilot` 分支；最近一次完整回归绑定提交 `400f88516cc2fa46f6113af118047b89138c2ebb`，部署骨架已推送至 `2f8c439e5878cbada47b6354db52d0385279b3d6`。浏览器主流程记录见 `docs/BROWSER_ACCEPTANCE_CP04.md`；该分支尚未部署。
