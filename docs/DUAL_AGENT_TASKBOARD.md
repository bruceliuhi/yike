# 意客 AI 双 AI 协作任务板（V0.2 完整获客版）

> **执行定位（2026-09-09 主线整合）：本文件是协作分工建议，当前功能编号、进度与验收证据以 [V0.2 实施任务书](V02_IMPLEMENTATION_TASKBOOK.md)为唯一台账；下表不能重置已完成工作或冻结已授权开发。** `6f449e6` 已将旧 DISCOVERY/SQLite 计划校正到 V0.2；当前正式代码入口为 `pilot/` 与 `desktop/`，旧 `app/` 仅作复用来源。现有 Mac 前端 Goal 继续执行，Windows 实机由用户手动运行脚本回传，不能假定已有可远控 Windows。仓库规则见[当前工作流](REPOSITORY_WORKFLOW.md)。

> 主仓：`xinghetech/yike-ai2026`
> 主分支：`main`
> 当前主线：以最新 `origin/main` 为准（初始基线 `0e20ffb`）
> 更新：2026-09-09

## 产品终点

面向有实际交付能力的服务商，交付完整闭环：

```text
登录/客户空间 -> 业务画像 -> 多平台真实采集 -> 持续监控
-> AI意向与原文证据 -> 商机复核 -> 人工确认后真实触达
-> 回复/跟进 -> Windows交付 -> 服务端部署与试用
```

旧 DISCOVERY MVP 是技术基础和验证子集，不是本任务板的最终上线标准。不得用本地 SQLite、模拟数据、静态页面或单平台 HTTP 200 宣称产品上线。

## 双 AI 分工

### Mac Codex：主实现、后端与发布集成

- 唯一负责 `main` 合并、迁移、服务端集成和发布判定。
- 负责账号/设备/执行协议、PostgreSQL 客户数据、任务调度、Skill 运行、评分复核、触达状态、回复跟进和生产门禁。
- 负责处理 API/数据库冲突，保存每个任务的提交 SHA、测试和证据路径。

### Win Codex：独立模块与 Windows 交付

- 只从最新 `origin/main` 建 `codex/win-<主题>` 分支。
- 负责平台适配器/解析器契约测试、R3 前端/API client、Electron/sidecar、安装更新和 Windows 实机证据。
- 不直接修改 Mac 正在编辑的 migration、事实表、租户隔离或服务端集成入口。

## 任务卡

状态：`READY`、`DOING`、`REVIEW`、`DONE`、`BLOCKED_INPUT`、`BLOCKED_DEPENDENCY`。

| ID | Owner | 分支（从任务开始时最新 `origin/main` 起） | 交付范围 | 依赖 | 上线验收 | Reviewer | 状态 |
|---|---|---|---|---|---|---|---|
| `SYNC-01` | Mac | `codex/mac-identity-execution-contract` | 对齐 parent authority、`AUTHORITY.md`、V02 计划与当前 main；列出旧 Discovery 分支的选择性迁移清单 | 无 | [对齐记录](SYNC-01_BASELINE_RECONCILIATION.md)已形成，待独立复核；不改写只读父仓、不整支盲合并 | Win | `REVIEW` |
| `V02-01` | Mac | `codex/mac-identity-execution-contract` | 客户激活/登录/退出、客户空间、设备绑定/撤销、平台连接、执行事件与 Origin/认证边界 | `SYNC-01` | 两客户/设备不可串用；退出/断开立即失效；桌面不持有服务端密钥或 DB 连接 | Win | `DOING` |
| `V02-02` | Mac | `codex/mac-multiplatform-data-api` | 平台能力注册、候选上传 API、PostgreSQL 事实模型、租户解析、整包事务、幂等和去重 | `V02-01` | 首发平台逐个可溯源；重复运行不重复入库；失败整包回滚；SQLite 不作为正式客户库 | Win | `BLOCKED_DEPENDENCY` |
| `V02-02-WIN` | Win | `codex/win-adapter-contracts` | MediaCrawler/平台适配器、解析器、标准化、平台 ID 冲突和可重开来源契约 | `SYNC-01` | 只依赖公开接口；不直连 DB；定向测试、secret scan 和跨平台路径检查通过 | Mac | `READY` |
| `V02-03` | Mac | `codex/mac-monitoring-executor` | 多平台持续任务、游标、租约/执行代次、账号锁、暂停/恢复、重试和部分成功 | `V02-01`,`V02-02` | 每平台多轮真实运行；无新增、失效恢复和旧执行者回写拒绝均有证据 | Win | `BLOCKED_DEPENDENCY` |
| `V02-04` | Mac | `codex/mac-skill-review-workflow` | 版本化通用/平台 Skill、证据提取、意向判断、人工复核和纠错 | `V02-02` | 原文引用、画像版本、反证和未知项可追溯；未复核不能成为已批准商机 | Win | `BLOCKED_DEPENDENCY` |
| `V02-05` | Win | `codex/win-r3-product-ui` | 八个入口、画像、任务、采集、监控、商机、触达、跟进、账号页面及 API client | `V02-01`，并行接入 `V02-02~04` | 空客户空间可完成配置、启动、复核、暂停/恢复；页面和真实 API 状态一致 | Mac | `BLOCKED_DEPENDENCY` |
| `V02-06` | Mac | `codex/mac-channel-capability` | 触达通道能力矩阵、来源主体到收件人的可核验映射、发送/回执/回复协议 | `V02-01` | 真实来源对象可判断可联系性；失败原因准确；不以测试账号替代获客闭环 | Win | `BLOCKED_DEPENDENCY` |
| `V02-07` | Mac | `codex/mac-outreach-confirmation` | 草稿版本、对象/渠道确认快照、幂等发送队列、未知结果对账和暂停 | `V02-04`,`V02-06` | 任一对象/内容/渠道/连接变化使确认失效；未经确认不发送；未知结果不盲重试 | Win | `BLOCKED_DEPENDENCY` |
| `V02-08` | Win | `codex/win-reply-followup-workbench` | 回复回流、未读/到期队列、负责人、跟进时间线和事实/平台事件区分 | `V02-05`,`V02-07` | 回复归属正确客户和商机；跨租户不可见；明细可复算统计 | Mac | `BLOCKED_DEPENDENCY` |
| `V02-09` | Win | `codex/win-release-lifecycle` | Electron/sidecar、凭据私有存储、安装/卸载、激活、更新/回退、休眠恢复 | `V02-01`，逐步接入 `V02-03`,`V02-06` | Windows 新机真实验收；不含 DB/Admin secret；取消/恢复和授权失效可追溯 | Mac | `BLOCKED_DEPENDENCY` |
| `V02-10` | Mac | `codex/mac-release-uat` | 集成、独立架构/代码/质量审核、部署、备份恢复、回滚、客户试用和发布清单 | `V02-02~09` | M1/M2/M3 证据齐全；私网 PostgreSQL、RLS/ACL、HTTPS、部署 SHA、真实端到端和客户 UAT 全部通过 | Win | `BLOCKED_DEPENDENCY` |

## 里程碑与上线判定

- **M1 技术可演示**：登录连接、逐平台真实首次采集、原始候选可核验。
- **M2 客户可试用**：持续监控、Skill 意向筛选、用户复核、统一商机工作台。
- **M3 完整付费版**：确认后真实触达、回复回流、跟进、Windows 交付、服务端实际部署、备份恢复和独立审核。
- M1/M2 不能对外表述为完整上线产品。M3 也只证明技术交付条件，仍需至少 3 家客户试用、实付、持续使用/续费意向验证商业成立。

## 协作与交叉验证

- 每项任务开始前 `git fetch origin`，记录 `base_sha`；禁止从其他 feature 分支分叉。
- PR 必须写明修改目录、依赖、测试命令、证据路径、已知缺口和回滚方式。
- 实现者不得做最终 reviewer：Mac 审 Win，Win 审 Mac；修复后复审同一 PR。
- Mac 负责短事务、迁移和最终合并；Win 不覆盖 Mac 正在修改的契约文件。
- 最低代码门禁：

```bash
uv sync --frozen --extra dev
uv run --frozen pytest -q
uv run --frozen python -m compileall -q app tests
node --check static/app.js
git diff --check
```

- 真实平台、真实账号、扫码、Windows、通道和客户回复是独立证据层；缺少时只记 `BLOCKED_INPUT`，不得用 mock 清除。
- Cookie、Token、API Key、Profile、二维码和私信内容不得进入 Git、数据库、日志或导出。
- 平台处罚、误发、重复骚扰、越权采集或敏感信息泄露立即停止。

## Gitee 工作流

```bash
git fetch origin
git switch -c codex/<主题> origin/main
git push -u origin codex/<主题>
```

PR 目标固定为 `xinghetech/yike-ai2026:main`。Mac 负责合并；未有 reviewer PASS、测试证据和回滚点的分支不得进入 `main`。
