# 原文详情简化 Implementation Plan

> 执行：使用 subagent-driven-development 完成一个小批次；用户已授权范围内自主细化、main 串行改动及压缩重复审核。原文打开链单独诊断，不以展示修改宣称修复。

**Goal:** 落实已批准的客户界面标准：原文、作者、发布时间优先，采集内部信息默认收起，时间不显示技术格式。

**Architecture:** 只调整 CandidateOriginalEvidence 的呈现，复用 formatDate；保留 time.dateTime 和原始 DTO、正文及来源未知状态。接收时间、观察时间放入默认关闭的“采集详情”；历史保持默认关闭。收起而不删除数据，避免历史证据丢失。

**Tech Stack:** React、TypeScript、Vitest/Testing Library。

## Chunk 1: 单组件差量

- [x] 修改 desktop/tests/ui/candidate-evidence-panels.test.tsx：先断言默认原文可见、内部时间不可见，展开后可见；检查可读时间及原始 dateTime、未知发布时间不借接收时间填充，历史逐字正文保留。运行该文件验证预期 RED。
- [x] 修改 desktop/src/renderer/pages/opportunities/CandidateOriginalEvidence.tsx：导入已有 formatDate，转换 EvidenceTime 可见文字；当前采集时间放默认关闭 details；不改作者、正文、来源核验和入库操作。
- [x] 定向运行 candidate-evidence-panels 与 public-author-evidence，必要 typecheck。审核同一批差量，不全量重测、不单独构包。
- [ ] 一次审核并提交 main；与已通过的31bdeeb下一候选合批。实际安装与用户链路未过前不标上线。

验证：初始新增夹具因发布时间早于父评论被合同拒绝，修正夹具后得到有效 RED 13通过/5失败（可见时间与默认折叠缺失）；GREEN 两文件19通过/0失败，typecheck退出0。原始JSON报告保留本地.runtime/candidate-evidence-{red,green}.json。根代理读取JSON及实际差量复核，独立Spec/Quality均GO；组件blob53b164d53f93b59593023f8621a9ce3fd4a1f4c2，测试blob943a750d149bd2bd589b59c93f691d17d0ad5c3d。此次仅展示改动，安装版仍0f81f76；不重构同字节旧包，不标原文访问修复。

## 原文打开调查（2026-09-14）

安装0f81f76从客户端打开无标题真实笔记6aa6534e000000002902df7a。普通Chrome页面实际显示“当前笔记暂时无法浏览 / 请打开小红书App扫码查看”，登录按钮可见；这不是已证明意客授权失效或帖子被删除。5篇已存原帖 note_url 均不含查询参数。main OPEN_EXTERNAL 仅 shell.openExternal；vendor/patches/mediacrawler/0002-yike-xhs-runtime.patch 的 store.xhs 明确移除 xsec_token 和 URL 参数，connectors/candidate_mapping.py 也要求裸 canonical URL。既有 native-link 设计仅允许输入链接保留公开参数，明确不放宽候选证据合同。

当前没有已有的只读原文查看器；登录 driver 完成后主动关闭浏览器，不能拿登录动作冒充原文打开。不能为测试导出 Cookie、改写云端证据 URL 或谎称浏览器已打开即核验成功。待验证方案应保留当前账号/设备隔离与凭据保护，不假定仅复用登录就能解决源站访问限制。

进一步已找到可复用的导航模式：app/platform_outreach_runtime.py 在既有隔离浏览器先打开原作者主页，再点击该页实际可见的精确笔记链接，临时参数只留在浏览器；tests/test_platform_outreach_runtime.py 覆盖该导航及缺失链接失败。但这是已确认发送上下文的运行器，不是通用只读查看入口，不能为看原文伪造发送上下文。此次无标题候选作者未知，不能凭匿名哈希拼作者主页。下一步应验证同会话只读导航（已知作者用原主页，未知作者仅可用原查询中实际找到的同一笔记链接），找不到则明确不可访问；不得搜索相似帖子代替原证据。
