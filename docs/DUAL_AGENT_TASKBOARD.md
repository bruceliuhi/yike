# 意客 AI 双 AI 协作任务板

> 主仓：`xinghetech/yike-ai2026`
> 主分支：`main`
> 初始基线：`0e20ffb`；当前主线以最新 `origin/main` 为准
> 更新：2026-09-09

## 目标与边界

本任务板只推进当前权威的 DISCOVERY MVP：B 站＋抖音授权采集、标准化去重、AI 评分、人工复核、草稿、人工联系登记和指标。不得把冻结的云端多租户、自动外联、绕过验证码或其他平台重新带入主线。

产品主链路：

```text
获客任务 -> 真实采集/导入 -> 商机识别 -> 回复草稿 -> 人工批准
-> 平台执行 -> 回复/访谈/报价结果记录 -> 指标
```

## 双 AI 分工

### Mac Codex（主实现与集成负责人）

- 持有 `main` 合并权和发布权。
- 负责 SQLite 事实契约、评分/复核/草稿/联系因果链、指标和最终集成。
- 负责处理跨模块冲突、迁移和最终验收。

### Win Codex（独立模块负责人）

- 只在自己的 `codex/win-<主题>` 分支开发，不直接修改 Mac 正在编辑的 migration、事实表或集成入口。
- 负责平台适配器/解析器的可移植实现、前端页面/API client、运行文档和对应测试。
- 不宣称真实 Windows、账号、扫码或平台采集完成；缺少真实输入只能记为 `BLOCKED_INPUT`。

## 任务卡

任务卡状态：`READY`、`DOING`、`REVIEW`、`DONE`、`BLOCKED_INPUT`、`BLOCKED_DEPENDENCY`。

| ID | Owner | Branch（均从任务开始时最新 `origin/main` 起） | 范围/目录 | 依赖 | 验收与证据 | Reviewer | 状态 |
|---|---|---|---|---|---|---|---|
| `SYNC-01` | Mac | `codex/sync-authority-baseline` | `AUTHORITY.md`、`docs/` | 无 | 逐项核对 parent authority、main 基线与未合并旧分支；形成差异清单，不盲目整支合并 | Win | `READY` |
| `YK-D04-MAC` | Mac | `codex/mac-score-review-workflow` | `app/`、`migrations/`、`tests/` | `SYNC-01` | 坏模型输出失败关闭；score/review/draft/contact 同 run 绑定；唯一主体和回复/访谈/报价因果链测试全绿 | Win | `READY` |
| `YK-D04-WIN` | Win | `codex/win-adapters-contract-tests` | `app/adapters/`、`tests/adapters/` | `SYNC-01` | B站/抖音输入映射、URL/时间/作者规范化和冲突 ID 处理；只依赖公开接口契约，不直连数据库 | Mac | `READY` |
| `YK-D05-WIN` | Win | `codex/win-review-ui` | `static/`、`app/web/`、`tests/web/` | `YK-D04-MAC`、`YK-D04-WIN` | 运行、线索、详情、跟进、指标五页可从空库打开；人工发送仍逐条确认；浏览器/API 测试通过 | Mac | `BLOCKED_DEPENDENCY` |
| `YK-D05-MAC` | Mac | `codex/mac-metrics-export` | `app/metrics/`、`app/exporter/`、`tests/` | `YK-D04-MAC` | 三层指标只读事实表；CSV 脱敏导出；终态结论真值表测试通过 | Win | `BLOCKED_DEPENDENCY` |
| `YK-D06-MAC` | Mac | `codex/mac-integration-gate` | `scripts/`、`tests/`、`docs/RUNBOOK.md` | `YK-D05-WIN`、`YK-D05-MAC` | pytest、compileall、JS 检查、diff check、空库浏览器主流程全绿；每个平台真实小批次单独记录 | Win | `BLOCKED_DEPENDENCY` |
| `YK-D06-WIN` | Win | `codex/win-portability-evidence` | `scripts/`、`docs/`、`tests/` | `YK-D04-WIN` | 在 Windows 新机验证安装/启动/停止/恢复路径；不能用模拟输入替代真实平台证据 | Mac | `BLOCKED_DEPENDENCY` |
| `REL-01` | Mac | `codex/release-mainline` | `docs/`、发布清单 | 全部任务独立 PASS | 复核所有 commit、证据路径、secret scan、回滚点；只通过 PR 合并 `main` | Win | `BLOCKED_DEPENDENCY` |

## 执行顺序

1. `SYNC-01` 先完成，确认 main 与当前权威文档一致。
2. `YK-D04-MAC` 与 `YK-D04-WIN` 并行，但 Win 只能依赖公开接口契约。
3. `YK-D05-MAC` 与 `YK-D05-WIN` 在 D04 双方 PASS 后并行。
4. `YK-D06-MAC`、`YK-D06-WIN` 并行做平台性验证。
5. `REL-01` 由 Mac 集成，Win 做最终交叉复核后才合并。

## 分支、提交与交叉验证规则

- 开始任务前必须 `git fetch origin`，记录 `base_sha`；禁止从另一条 feature branch 直接分叉。
- 每个任务一个分支、一个可回滚提交序列；PR 描述必须包含：修改目录、依赖、测试命令、证据路径、已知缺口和回滚方式。
- 实现者不得担任自己的最终 reviewer：Mac 审 Win，Win 审 Mac；修复后必须复审同一 PR。
- 合并前最低门禁：

```bash
uv sync --frozen --extra dev
uv run --frozen pytest -q
uv run --frozen python -m compileall -q app tests
node --check static/app.js
git diff --check
```

- 不使用 mock、fixture、静态页或 HTTP 200 证明真实采集、联系、回复或商业成功。
- Cookie、Token、API Key、Profile、二维码和私信内容不得进入 Git、SQLite、普通日志或导出。
- 平台处罚、误发、重复骚扰、越权采集或敏感信息泄露立即停止并记录风险事件。

## Gitee 协作命令

```bash
git fetch origin
git switch -c codex/<主题> origin/main
git push -u origin codex/<主题>
```

PR 目标固定为 `xinghetech/yike-ai2026:main`。Mac 负责合并，Win 负责交叉复核；未通过 reviewer PASS 的分支不得进入 `main`。
