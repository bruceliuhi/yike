# 代码与文档仓库工作流

生效：2026-09-09，依据用户本轮明确指令。

## 唯一产品代码目标

产品仓库为 [yike-ai2026](https://gitee.com/xinghetech/yike-ai2026)，集成分支和默认分支均为 `main`。前端、客户端、后端、Skill、测试、构建脚本及产品功能都在这里交付。`ike-ai2026` 是随后被用户更正的名称，不是另一个提交目标。

新功能流程：

```sh
git fetch --prune origin
git switch main
git merge --ff-only origin/main
git switch -c codex/<主题>
# 开发、验证、独立审核、提交
git fetch origin
git merge origin/main
# 如有合并修改，按影响范围重新验证和审核
git push -u origin codex/<主题>
# 将审核后的功能分支合并回 main，再推送 main；可通过 PR 完成
```

先检查工作树；有未提交改动时妥善保留或使用隔离 worktree，不覆盖其他任务。推送 `main` 使用正常快进/合并，遇到并发提交重新获取并整合，不强制推送。旧分支暂时保留作溯源，不能因“全部代码归 main”而把未经评估、过时或相互冲突的路线整批覆盖当前代码。

## 权威文档过渡期

[yike-ai](https://gitee.com/xinghetech/yike-ai) 暂时保留为只读权威文档仓库。只读表示本阶段不向它提交或修改内容；本轮没有更改成员权限，也没有归档该仓库。

本仓库已有设计基准、实现台账、运行说明、内部依赖溯源和验收证据随产品代码维护。用户最新要求优先于旧文档中的历史范围；需要新增治理决定时明确记录其来源，不暗中改写只读仓库。

等产品稳定后，再核对并迁移**必要**治理文档至 `yike-ai2026/docs/authority/`，保留来源提交和迁移索引，然后归档 `yike-ai`。本轮不提前迁移、不新建该目录占位，也不将现有文件删除或批量复制过去。

## 本轮已核验

- 远端 `main` 已从 `0e20ffb` 快进到已审查的 R3 客户端候选 `615e340`，包含 `10ab8b6` 的前端/桌面实现与绑定审核。
- Gitee 仓库设置显示默认分支 `main`；`git ls-remote --symref origin HEAD` 同样返回 `refs/heads/main`。本地 `origin/HEAD` 已同步。
- 本轮收尾工作在最新 `main` 上创建的 `codex/main-integration` 中验证并整合，实际纳入内容和绑定审核见[主线整合验收](qa/main-integration/REVIEW.md)；提交到主干不表示这些产品能力已全部接通或已上线。
- 具体功能状态和验收限制见 [R3 UI 实施记录](UI_R3_IMPLEMENTATION.md)及[实施任务书](V02_IMPLEMENTATION_TASKBOOK.md)。Windows 实机由用户按脚本执行并回传结果，macOS 验证不替代该项。
