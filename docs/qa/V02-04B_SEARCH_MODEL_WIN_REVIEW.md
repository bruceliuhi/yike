# 04B 搜索建议模型：Win 独立切片

日期：2026-09-09。代码 `e26c7a3f3b850620bdf0d2f1af334730159a2f77`，基线为保留 Mac 手机号登录的合并 `b3996bc`。仅新增模型适配器及专项测试，没有修改默认入口、共享数据库、客户端或任何采集/联系功能。

## 范围与证据

已交付：已确认画像正文 → 可编辑搜索词/排除词、理由、逐字原文依据及未知项。引用必须非空且逐字存在于传入正文，搜索建议不是已发现商机，也不是完整事实核验或执行授权。跨行业提示不限定 AI 开发或展台行业。

- 实现者 TDD：先缺模块 75 RED → 75 GREEN，再缺适配器 RED → GREEN；新增 Node.js/ASP.NET/Vue.js 合法词及巨大整数 timeout 反例均先 RED 后修复，最终 187 passed/0 skipped。
- 独立规格 `strategy_preflight`：187 passed/0.26s，PASS。独立代码/架构/质量 `connection_cross_review`：187 passed/0.25s，PASS，无本切片新增 P1/P2。
- 根代理提交前复现：187 passed/0.26s，0 failures/skips。严格请求、原文引用、坏/歧义 JSON、截断/拒绝、流式字节上限、无重试/重定向、安全错误和真实 usage 解析均有定向测试。
- 合并 Mac 手机号登录时，工作树相关 Python 集合 315 passed/2.22s（包含本适配器 187），桌面相关 37 passed/5.34s，TypeScript 检查通过；不是手机真实收码或 Windows 手机登录 ACK，不与其他历史测试相加。
- 上述模型传输使用 httpx.MockTransport，没有调用真实模型供应商或发送客户资料。结果证明请求与解析边界，不证明真实建议质量。

冻结文件 SHA256（审核工作树字节；Git 换行归一化不改变源码）：

- `pilot/search_suggestion_model.py`：`bffcf993e853bcf695cb888089f6cf2ad4c830eee2a2f1f6a874ddd6ebfedc01`
- `tests/test_search_suggestion_model.py`：`c6687892a263227c2e7881d8ff2acc204ddadd92721374ccc9aa97c2fb55bc56`

## 接入前仍须完成

1. `description` 原样发送，不是输入脱敏器；上游必须核定可披露内容与授权，确认画像本身不等于允许全部自由文本外发。搜索词的明显联系方式过滤不能代替这一检查。
2. httpx timeout 是分阶段 I/O 超时，不是整个调用的截止时间；后台仍须落实总时限、在途调用和实际关闭证明。可信注入客户端须自带无隐式重试保证。
3. Win 正继续独立 PostgreSQL 请求/配额/原回执持久层（110）、随后认证 router 和既有 05C 页面。共享入口由 Mac 串行接收；108 保留资料、109 保留 Mac 认证。没有策略版本、预算授权、真实“多找类似”或默认能力启用。
4. 真实供应商、两类真实业务效果、客户端端到端及客户试用待验收。04B 和整体 Goal 保持 IN_PROGRESS；本报告不是 Mac ACK 或产品上线。
