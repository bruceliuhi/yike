# 主线整合质量审核

- 日期：2026-09-09。
- 绑定代码候选：`cd642bddfc1238853a21a7aef39a2c0432dbe38a`。
- 对照主线：`e7c94a9`；本轮为正常整合及选择性迁移。
- 结论：**PASS，限定于此次代码主线整合；未发现本审核范围内新增 P0/P1 阻断。** 不代表完整产品、Windows 安装包或生产发布通过。

## 独立范围

本次交叉检查其他成员编写的 Windows 构建证据工具与人工模板、MediaCrawler 源码打包器的三项修复、对应安装校验及回归测试，并检查仓库工作流、当前权威、实施任务书和旧并行任务板的范围说明。

**排除本人编写的视觉 harness、后端 store / research_import 选择性迁移及其测试。** 下文可引用主任务汇总的执行结果，但不将这些自作模块记为本人独立代码审核通过。既有 R3 运行源码及历史 Mac 包沿用各自绑定审核，不在此重复全量视觉验收。

## 本次直接检查与执行

| 项目 | 结果与范围 |
| --- | --- |
| 候选身份 | 实际 HEAD 为上述完整 SHA；审核开始时工作树干净 |
| Windows 证据来源 | 重算 [writer 记录](../ui-r3/windows-evidence-writer-check.json) 的 PowerShell、JS writer、测试和人工模板四个输入摘要，与候选 commit blob 全部一致 |
| Windows writer 回归 | 在 `desktop/`、Node 24 环境执行 `./node_modules/.bin/vitest run tests/windowsBuildEvidence.test.mjs`：**7 passed** |
| 打包器回归 | 仓库根执行 `.venv/bin/python -m pytest tests/test_vendor_packaging.py -q`：**13 passed** |
| 文档范围 | 产品集成目标为 `yike-ai2026/main`，新功能从主线创建 `codex/<主题>`；`yike-ai` 暂时只读，正式治理迁移与归档留待后续，不冒称已执行 |

Windows 工具逐阶段持久化状态和退出码，失败后的未执行阶段保持 `NOT_RUN`；部分完成不会返回构建成功，人工验收始终为 `UNTESTED`。产物仅接受 `out/` 内实际文件，校验符号链接后的真实路径并计算大小与摘要。输出不保存环境变量、原始凭证、变更文件名或异常全文；dirty 与 Git 不可用均显式保留，不能将 dirty 构建当作提交的精确产物。人工模板覆盖安装、启动、草稿、三步检查、退出重启、单实例、卸载和三档系统缩放。

打包器修复已与代码和测试相互核对：已有 bundle / manifest（含符号链接）不覆盖；私有临时 bare 仓库承载打包引用，不改变源 checkout 的 refs；当前树及所带历史中的任意层级 `.env*` 路径均拒绝。发布使用同文件系统完整临时文件和排他硬链接，异常清理只处理本次发布且 inode 仍相同的输出。安装路径继续校验包、锁、commit、patchset 与许可证摘要，没有跳过原有 runtime 校验。

这些打包回归使用明确的本地 fixture 仓库。当前并未证明真实上游包已分发或采集器已经接入 Electron；路径检查也不替代源码及 Git 历史的内容级秘密扫描。[运行手册](../../RUNBOOK.md) 已保留这些限制和强制终止后的残留 manifest 处理说明。

## 主任务提供的同树验证

本次没有重复执行以下完整套件；已核对 [checks.json](checks.json) 的确切命令、结果与工具输出来源，并保留其适用范围：

- 桌面 `npm test`：**27 文件、238 passed**；`npm run typecheck` 通过。
- `uv run --frozen --extra dev pytest -q tests/test_import_atomicity.py tests/test_research_import.py tests/test_ui_api.py tests/test_pilot_web.py tests/test_pilot_contracts.py tests/test_vendor_packaging.py`：**95 passed，0 skipped**。数据库仅为本轮隔离 PostgreSQL，管理员与非超级用户 / 无 RLS bypass 的应用连接分离；连接字符串不写入报告。
- Secret scan、Shell 语法、Python 编译与差异检查通过。上述定向通过不扩展为历史全仓 Python 测试全部通过。
- Windows CLI 在 macOS 上拒绝非 Windows 宿主，并保留失败报告；这项正确失败不等于 Windows PowerShell 或安装流程已验收。

汇总及交付边界见 [主线整合验收](REVIEW.md)。本轮未重新构建 Mac 包，不将新的 harness / Windows 工具测试数覆盖为旧 Mac 包的构建测试数。

## 文档一致性与后续限制

[AGENTS.md](../../../AGENTS.md)、[AUTHORITY.md](../../../AUTHORITY.md) 与 [仓库工作流](../../REPOSITORY_WORKFLOW.md) 指向相同产品主线；现有设计和验收继续随产品维护。旧 [双 AI 任务板](../../DUAL_AGENT_TASKBOARD.md) 及其 [执行计划](../../superpowers/plans/2026-09-09-dual-agent-mainline-development.md) 首部已明确降为旧 DISCOVERY / SQLite 参考，不能用其双平台或冻结条款撤销当前多平台、PostgreSQL、R3 和客户端要求。任务书继续保持未完成能力的待开发状态，没有把整包事务或源码打包完成记为平台采集完成。

Windows PowerShell 解析、Node 缺失兜底、实际 x64 构建、安装 / 启动 / 退出 / 重启 / 卸载和 100% / 125% / 150% 缩放仍待用户在 Windows 执行。真实平台连接、采集、监控、收发、完整同状态视觉对照以及生产环境验收也仍未完成。这些限制已在当前交付范围中明确，不阻断本次代码整合，但不能据本报告对外宣称完整产品已上线。

本次仅新增质量报告，不修改源码、不提交、不推送。后续代码变化、合并冲突修复或新包生成须按影响范围更新验证与绑定审核。
