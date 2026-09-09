# 仓库协作约定

用户于 2026-09-09 确认：

- 所有产品代码、前端页面、客户端、服务端和功能交付均提交到 `https://gitee.com/xinghetech/yike-ai2026`，最终合并目标为 `main`。
- 新功能从最新 `origin/main` 建立 `codex/<主题>` 分支，完成必要验证及独立审核后合并回 `main`。不再把 `codex/customer-pilot` 当作默认集成分支。
- `https://gitee.com/xinghetech/yike-ai` 暂时是只读的权威文档仓库；不要在那里提交产品代码或修改文档。
- 产品稳定后再迁移必要治理文档到本仓库 `docs/authority/`，然后归档 `yike-ai`。这是后续安排，本轮不执行迁移或归档。
- 本仓库现有设计、实现台账、验收记录继续随代码更新；保留历史证据及其适用版本，不将测试通过、提交到 `main` 或设计完成写成生产上线。

先读 [仓库工作流](docs/REPOSITORY_WORKFLOW.md)、[当前整合状态](docs/INTEGRATION_STATUS.md)、[产品与开发约定](AUTHORITY.md)及实施任务书。存在冲突时，用户最新明确要求优先；本文件不重新授权外部消息、支付或生产部署。
