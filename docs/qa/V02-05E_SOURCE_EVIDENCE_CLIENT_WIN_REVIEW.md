# 05E 固定原文证据客户端：Win 限定验收

执行：2026-09-10，CodexWin；基线 `ff623eda1d7c037a279517ca668ecc467af0cecc`。
按[已审分片计划](../superpowers/plans/2026-09-10-win-fixed-source-evidence.md)消费 Mac 115/[固定证据合同](../contracts/V02_OPPORTUNITY_SOURCE_EVIDENCE.md)，不修改共享后端、迁移或正常运行装配。根代理唯一 Git 写入者；分工和状态仍以[任务书](../V02_IMPLEMENTATION_TASKBOOK.md)为准。

开发中正常快进同步 Mac `27ed49949c3c8aa7baab12cdff159057b96c9890`，保留其资料/跟进恢复与验收记录；与本片文件无交叉覆盖。`useResource` 没有变化，`hooks.ts` 仅新增旧跟进操作键识别。Mac 的全量/Mac 包证据不记为 Win 本轮重跑。

提交前再次正常快进至 Mac `eb507bfbf18c1f90b0216cd25cb8d79908c35cc0`，保留其正常 CLI 装配/容器规则修复及签名载荷接口认领；该批 14 文件无 desktop、shared evidence、store 或 ui_api/web 改动，Win 已审字节保持不变。根代理额外在 Windows 执行 `tests/test_pilot_runtime.py`、`tests/test_pilot_provision_cli.py`、`tests/test_pilot_runtime_container_layout.py`：**21 passed in 1.25s**，这是新来件纯测试兼容检查，不是 Mac 真实 PG/容器证据在 Win 重跑。

## 范围与验收边界

Task1 是严格 DTO 与现有普通详情/R4 读取的接入；Task2 才是 P11/R4 展示、优先研究路径补读及页面生命周期验证。原文、原帖标题、父评论、逐字引用、作者及各事件时间不得互相冒充。服务端校验快照摘要，客户端保留并检查格式，不另造哈希算法。历史 `CAPTURED` 不表示当前来源可访问或已允许联系。

列表省略完整证据保持未加载，只有明确的 `UNAVAILABLE/NOT_CAPTURED` 表示未留存。详情字段缺少或损坏必须失败并可重试，不制造无证据状态。新 `sourceEvidence` 不覆写旧 `sourceEvidenceVersion`、`sourceObservedAt` 或 R4 分类绑定。

浏览器 GET 透传 AbortSignal；现有桌面 IPC 没有物理取消协议，仅在调用前和采用回复前检查取消，页面另保留已有账号/空间/商机 generation 隔离。本片不增加新 IPC、不自动打开来源、不分析/采集/联系。

## 测试先行与当前证据

- 根代理先添加普通客户端和 R4 领域反例：两文件 67 项中 15 项按预期失败，分别暴露固定证据被丢弃、未校验透传、详情缺字段/错身份被接受及取消未传递/未阻止迟到采用；原 52 项通过。
- DTO 作者在可导入 stub 上观察 23 项中的 8 个合法输入反例失败，15 个拒绝反例通过；不是模块缺失或测试环境错误。
- 根代理独立运行既有 main 传输及机会页面相关三文件：29 passed；这是 Task2 修改前的回归基线，不是新页面验收。
- 根代理复跑 Mac 纯固定证据合同 `tests/test_opportunity_evidence.py`：14 passed；不是实际 PostgreSQL 或平台消费 ACK。

收口时根代理进一步复现尾部残缺高代理项和超过 2MiB 正文被接受；作者补两项 RED→GREEN，修正 Unicode guard 与总 JSON UTF-8 字节上限，未缩小单条合法正文限制。测试路径的数字索引类型错误也已修正。Task1 中间快照根代理和审核者各跑三文件 **98 passed**、全桌面类型检查通过；旧 renderer 构建 4773 模块。最终 DTO 作者冻结后又有一次整理，因此不把中间审核摘要 `C856…` 绑定最终文件；最终文件已由下述 269 项批次重新执行。

实际 HTTP/PG 首跑在合成当前状态准备阶段失败：受限应用角色无 `pilot_opportunities` 更新权，因此不能用旧 `set_source_status` 改夹具。该失败发生在 Node 消费前，隔离容器已经精确核对并移除；不会为测试扩大生产应用权限，改由独立数据库的管理员夹具准备状态，实际客户读取仍使用受限角色。

修正夹具后根代理实际重跑：**1 passed in 2.77s / 0 skipped**，`EXACT_TEMP_POSTGRES_REMOVAL_CONFIRMED`。专属测试为 `tests/test_desktop_opportunity_http_postgres.py` → `desktop/tests/integration/opportunity-evidence-live.test.ts`。合成 COMMENT 经过真实策略、112/113/115 人工 INCLUDE 持久化，经共享 `build_app`、认证 HTTP、受限 PG、产品 main client 和 renderer `service.opportunity()` 读取；完整 nested 快照逐值一致，null 作者/父评论时间/链接如实保留，引用与主体正确，当前 BLOCKED 不覆盖纳入时 OPEN，退出 401、跨客户 404。管理员只准备一条精确 tenant/opportunity 状态，读取没有扩大生产权限。Node 子进程无数据库环境变量、凭据不进 argv，日志遮蔽合成 token。普通未配置 Vitest 明确跳过此 live 用例，不能算实际 PG 通过；本次真实运行没有跳过。

## Task2 页面接入与最终批次

- P11 复用现有蓝白 R4 版式，展示固定正文、公开作者、来源链接、来源发布/采集观察/服务收到/纳入留存四种时间；评论、原帖标题和父评论明确分开。长正文只折叠视口，不删正文；逐字引用注明判断维度和对应字段，版本/模型/规则明细默认折叠。私有画像引用只显示数量。历史留存不代表现在仍在采购或允许联系。
- R4 研究记录已有有效证据时不二次读取；旧研究记录缺少该字段才补读普通详情，核对机会与画像身份，仅补独立 `sourceEvidence`。切账户/商机取消或迟到返回不得回填旧证据。损坏、缺少或网络失败显示可重试错误，不伪装成明确未留存。R4 UI 先有 9 个预期 RED，修正后 30 passed；普通面板先有 4 个预期 RED，再全部通过。
- 非作者发现 P12 旁栏仍把旧 excerpt 标为“原文摘要”，会与新固定正文混淆。先加入实际 OutreachPage 反例，1 failed（其余 5 项由筛选排除）；仅改标题为“旧版摘录（非固定原文）”，样例另标“公开样例摘录”，整文件 6 passed。不更改 Mac 新草稿恢复、发送核验及幂等逻辑。
- 最终根代理 **20 文件 / 269 passed / 0 skipped**（03:32:08，Node 24.19），集合见命令；类型检查 exit 0。最终 DTO 文件 SHA-256 为 `68f81057686e13112d19ff4b8d3c919f63702a77b2dc8643dbf40608e834d8fe`，已在此批次实际执行。
- 生产排除脚本使用真实 renderer 入口与配置构建，仅改变输出目录；**4774 transformed / 4773 graph modules，manifestHarnessReferences=0，failures=[]**。新增 `tests/fixtures` 同样排除在生产模块图之外。`existingAsarChecked=false`，不把本轮 renderer 构建当新 Windows 安装包或包内验收。

可复现的最终桌面批次（在 `desktop/`，Node 24；各集合重叠不相加）：

```text
node node_modules/vitest/vitest.mjs run tests/opportunitySourceEvidence.test.ts tests/ui/client.test.ts tests/ui/r4-opportunity-research-domain.test.ts tests/ui/r4-opportunity-research-ui.test.tsx tests/ui/opportunities.test.tsx tests/ui/fixed-source-evidence.test.tsx tests/ui/outreach.test.tsx tests/ui/send-confirmation.test.tsx tests/ui/outreach-reconciliation.test.tsx tests/serviceClient.test.ts tests/visual
node node_modules/typescript/bin/tsc --noEmit
node tests/visual/verify-production-exclusion.mjs
```

实际 PG 使用已有 Win 一次性容器夹具 `.runtime/research-strategy-pg.ps1 -Evidence`；Python 为 `.runtime/venvs/win-device-review/Scripts/python.exe -X utf8`。复现环境由 Python 专属测试读取 `YIKE_IDENTITY_TEST_DATABASE_URL` / `YIKE_IDENTITY_TEST_APP_DATABASE_URL`，`YIKE_EVIDENCE_LIVE_NODE_BINARY` 选择 Node 24；不要配置生产库。

## Windows 浏览器走查

Playwright CLI 实际驱动 Edge，隔离 `127.0.0.1:18794` R4/P11，明确 TEST 夹具，无客户库、真实模型、采集或发送。按 frontend 技能保留现有界面并只增强证据阅读；没有以静态截图代替交互验证。

- **1440×1000**：原文与联系准备两栏可读。合成正文 1426 字符，折叠高度 140px、展开 448px、滚动内容高度 1237px；展开前后字符完全保留，`white-space: pre-wrap`。按钮 `aria-expanded` 随点击变化。
- **960×600**：单列，正文及联系面板宽 713px，右边界 921px 在内容宽 945px 内；页面 `scrollWidth=clientWidth=945`，无水平溢出。版本明细实际点击展开，64 字符摘要换行，四种事件时间与评论归属明确。
- 切“项目变化”实际进入 compact 面板，固定正文、来源按钮、历史不授权说明均保留；既有时间线照常展示。点击“生成联系草稿”沿既有路由进入 P12，未发送，旧摘录标签明确。P12 带 CAPTURED 的完整判断由真实页面定向用例验证，不拿此普通详情 UNAVAILABLE 的视觉夹具冒充。
- 已查看三张实际截图：`.runtime/output/playwright/fixed-source-evidence-20260910/fixed-evidence-1440.png`、`fixed-evidence-960.png`、`fixed-evidence-versions-960.png`；同目录 `.playwright-cli/` 保留快照/控制台。唯一控制台 error 是隔离 Vite 的 `favicon.ico` 404，无页面运行异常。上述仅为 Windows 浏览器，不是打包 Electron 实机发行。

## 独立审核与剩余边界

非作者 `fixed_evidence_task1_review` 对最终 Task1+Task2 **SPEC / 代码 / 架构 / 质量 PASS，0 项未解决 P1/P2**，P12 旧摘录标签问题已复核关闭；独立最终字节测试 **7 文件 150/150**、短句教练 **1 文件 31/31**、类型检查 exit 0、DTO 7/7 独立探针通过。它们与根代理批次重叠，不相加。最终 DTO 摘要明确更正为上述 `68f810…`，不沿用中间摘要。

同一非作者对 `27ed499..eb507bf` 的限定集成复核 **PASS，0 新增 P1/P2**：14 文件无相关入口耦合或已审字节变化，最终源码/测试摘要及本文 DSN/证据边界核对一致，不重复整批 05E 测试。根代理 `git diff --cached --check`、仓库 `secret_scan.sh` 通过；已关闭本次独占 Edge 会话和 Vite，保留本地截图，临时 PG 已精确移除。

最终审核绑定（本地 SHA-256，不是服务端证据摘要）：

```text
d004d1f3cb73c1afa71bbc97e5b71936698581920d663cc4c616b819fbd89021  desktop/src/renderer/pages/Opportunities.tsx
beaae21fd30e4d679174dc3a4e66723eea736cfde70aa6f51fc4fc51a87cfc96  desktop/src/renderer/pages/opportunities/OpportunityEvidence.tsx
8d86c77ec366ddc7abacf73f2b12a91285fdf778915439388e0ec8c969edfb50  desktop/src/renderer/pages/opportunities/FixedSourceEvidence.tsx
5029e64b390d834c932bfb2b16f6b17e6969a9ad416a0bd9a28cf775a152ddcf  desktop/src/renderer/pages/outreach/ContactEditor.tsx
9ca7f00001313e9fa61b4afa15f63732e01d974902ca946a443678d6e5e34bd3  desktop/src/renderer/base.css
14518ecd7cc2dc98bbb70f819bc6f9b05d51de9b198887bd6d2c8de9bc47e469  tests/test_desktop_opportunity_http_postgres.py
699b58bfc3cd17b9d4c8bc03a60e0781dda068ad81fdd6a2bc0420dcccd2b41e  desktop/tests/integration/opportunity-evidence-live.test.ts
```

真实平台来源、P07 原始候选/独立核验及完整 05G、真实模型效果、确认收发、Windows 发行和客户试用仍需接续。Mac 正常 CLI 装配/最小签名载荷接口保持原所有权；Win 接续设备 HTTP 与候选消费。05E/PH-F06 父项和整体 Goal 继续，原文证据、多找类似、短句建联均不后排到 V1.1。
