# 当前整合状态（供后续 AI 交接）

更新时间：2026-09-09。产品集成目标：`yike-ai2026/main`，不再使用 `codex/customer-pilot` 作为主干。新功能从最新 `main` 创建 `codex/<主题>` 分支；文档仓库分工见[仓库工作流](REPOSITORY_WORKFLOW.md)。

## 整合记录

下表记录已经纳入的工作及其验证范围。分支会持续前进，当前 HEAD、远端一致性与工作树状态应在接续工作时实际检查，不以本文件代替 git 状态。

| 提交 | 内容 | 状态边界 |
|---|---|---|
| `9c092be` | 纳入 `skills/ai-project-lead-research-v1/` 版本化研究 Skill | 规则、证据、分级、去重和评测契约已入库；尚未接入实际平台连接器、调度器或模型运行入口 |
| `3c854b8` | 纳入 `desktop/` 安全 Electron 壳候选 | 已通过本地单测、类型检查和 renderer 构建；只证明桌面壳候选，不证明 sidecar、Windows 安装、平台采集或真实触达 |
| `d9f74a5` | 更新 V02 任务台账，记录桌面壳提交 | V02-04、V02-09 为 `IN_PROGRESS`，不是 `DONE` |
| `a9f4207` | 搜索条件建议设计 R2：P06/P19/P20 与交互约定 | 画像自动建议、可编辑词、人工修改保护和最终配置确认已进入设计；整套仍待用户确认，真实建议服务尚未实现 |
| `10ab8b6`、`615e340` | R3 前端、桌面候选及绑定独立审核 | 已合并并推送 `main`；20 页可访问、Mac 候选可运行，不代表所有可用服务交互与真实平台能力已经完成 |

最新图册入口见 [R3 精修基准](../design/v02-suite-r3/README.md)。整套图册及关键状态已于 2026-09-09 获得实现授权，旧 R2 图册保留。上表旧提交的“待确认”描述是当时状态，不覆盖当前授权。当前实现、逐页证据和限制见 [R3 UI 实施记录](UI_R3_IMPLEMENTATION.md)，不要用设计图或文档替代业务功能验收。

## 既有验证记录

以下命令结果来自上述 Skill/桌面壳提交的对应环境；R2 设计检查另见 [图册验证记录](../design/v02-suite/VALIDATION.md)。

R3 候选 `10ab8b6` 的更新验证为桌面 216 passed、UI API/试用页 62 passed、隔离 PostgreSQL 接口 22 项通过及真实 macOS 运行；绑定审核见 [R3 实施审核](qa/ui-r3/IMPLEMENTATION_REVIEW.md)。这些结果只适用于相应提交及环境，Windows 实机、生产部署和未接通后端仍待验收。下面 2 passed 是桌面壳的历史记录。

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
