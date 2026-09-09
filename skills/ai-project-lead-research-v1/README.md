# AI 项目商机研究 Skill v1

这是从本机 `ai-project-lead-research` Skill 整理进意客 AI 仓库的版本化规则包，服务于 V0.2 的 MP-01 / V02-04。

## 边界

- 只负责研究规则、证据提取、分级、去重、覆盖记录和联系草稿。
- 不负责平台登录、采集连接器、调度、模型调用、评论、私信或发送。
- 外部发送必须由产品的确认队列和用户人工批准流程执行。
- 不包含 Cookie、Token、验证码、私信历史、账号资料或真实候选数据。

## 组成

- `SKILL.md`：触发条件、输入输出、研究流程和安全边界。
- `references/search-and-coverage.md`：从业务问题和可交付物扩展搜索表达与平台覆盖。
- `references/qualification-and-evidence.md`：买方资格、证据、分级、联系决策和短开场。
- `references/evaluation.md`：离线反例、真实采样、持续使用和损耗诊断。

运行入口、平台规则和候选 API 由 V02-01/V02-02/V02-04 另行实现与验收；本包被加载或测试通过，不代表平台已接通或已产生商业结果。
