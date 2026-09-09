# 当前整合状态（供后续 AI 交接）

更新时间：2026-09-09。当前分支：`codex/customer-pilot`。

## 已整合并推送

当前 Gitee 基线为 [`d9f74a5`](https://gitee.com/xinghetech/yike-ai2026/commit/d9f74a573e28918ce1951eb562a036fc60235c0b)，本地与远端 SHA 一致，工作树 clean。

| 提交 | 内容 | 状态边界 |
|---|---|---|
| `9c092be` | 纳入 `skills/ai-project-lead-research-v1/` 版本化研究 Skill | 规则、证据、分级、去重和评测契约已入库；尚未接入实际平台连接器、调度器或模型运行入口 |
| `3c854b8` | 纳入 `desktop/` 安全 Electron 壳候选 | 已通过本地单测、类型检查和 renderer 构建；只证明桌面壳候选，不证明 sidecar、Windows 安装、平台采集或真实触达 |
| `d9f74a5` | 更新 V02 任务台账，记录桌面壳提交 | V02-04、V02-09 为 `IN_PROGRESS`，不是 `DONE` |

远端在此基础上还包含设计审查合并提交；不要用设计图或文档替代业务功能验收。

## 已验证命令

- `uv run --frozen pytest -q tests/test_research_skill_contract.py`：2 passed
- `npm test -- --run`（`desktop/`）：2 passed
- `npm run typecheck`（`desktop/`）：通过
- `npm run build:renderer`（`desktop/`）：通过
- `bash scripts/secret_scan.sh`：clean
- `git diff --check`：通过

完整 Python 回归当前仍有既有日期窗口相关失败；本次没有把它表述为全仓通过，也没有把失败升级为新功能结论。

## 未整合内容及原因

- `codex/self-use-auto-public-reply-v1` 的自动公开回复、资格闭环和旧数据库迁移没有整批合并；它属于不同权威路线。需要时只能按 V0.2 的“确认后发送”契约选择性迁移并重新审核。
- 父仓库的 `output/`、截图、PDF、SQLite 和浏览器运行记录没有批量复制；其中可能包含临时事实或敏感数据。可将脱敏规则、反例和 fixture 逐项提炼到 Skill 评测目录。
- 旧 `codex/authorized-dual-platform-mvp` 是当前基线的祖先，没有额外本地提交需要合并。

## 后续 AI 必须遵守

1. 先读 `AUTHORITY.md`、本文件和 `docs/V02_IMPLEMENTATION_TASKBOOK.md`。
2. 将 Skill 规则层、平台连接器、任务调度、触达队列和 Windows 交付分开推进。
3. 不把 `SKILL.md` 存在、测试通过、设计完成或页面可打开写成平台已接通、真实采集、真实发送或商业成功。
4. 新代码使用独立提交和独立审核；未经用户确认不得发送外部消息，不得绕过验证码、限流或平台风控。
