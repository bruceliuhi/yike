# 联系草稿客户端接入

> **For agentic workers:** Use subagent-driven-development. 按用户要求仅定向验证、整批一次独立审核，不重复全量构包。

**Goal:** 普通客户端可读取、保存并恢复本人评论/私信草稿，不再只保存在当前页面。
**Architecture:** 复用121及现有三个认证HTTP接口、R4编辑器与pending账本。客户端携带开始编辑时的原回执作为CAS前驱，保存/读取不授权发送。
**Tech Stack:** React/TypeScript/Zod，现有FastAPI/PostgreSQL。

## Global Constraints

- 按已批准 `UI_SHORT_COACH_CONTRACT.md` 实施，不扩模型生成或外部发送。
- 评论/私信及用户/客户空间隔离；公开样例不访问客户草稿接口。
- 原请求未知不解锁，不把普通404/409/超时当确定未保存。
- 前驱仅从已采用的最新草稿或本人成功回执推进，不能在保存时偷偷取最新版本。
- 迟到读取不得覆盖人工编辑；旧窗口冲突保留原文。恢复版本、账号和对象，保留保存期间的新修改。
- 用户要求省token：复用已有后端验收；本批定向TS/UI、一次真实HTTP/受限PG客户端联验、类型检查及一次renderer构建；不重复全套后端测试或桌面打包。

## Task 1: 固定传输和运行时校验（Root）

- [ ] RED：新增 `desktop/tests/contactDraftService.test.ts`，普通service挂载、三个固定路径、完整hash/绑定、非法输入、仅精确draft_not_found为空、会话切换、错误不吞。
- [ ] `desktop/src/shared/contactDrafts.ts` 提供保存/原请求/latest请求schema；`domain/shortCoach.ts`复用保存schema，不复制摘要规则。`DraftSaveInput`新增可选 `previousRequestId:string|null`，不入摘要。
- [ ] `services/shortCoach.ts`追加可选 `latest(opportunityId,channel,signal?):Promise<DraftSaveReceipt|null>`，保持已有测试适配器兼容；生产适配器三个方法齐备。
- [ ] `services/contactDrafts.ts`通过既有transport/session校验，验证成功回执及当前空间；latest只把精确404 draft_not_found转null。`client.ts`挂载、`shared/contracts.ts`与`main/servicePolicy.ts`固定路由，无任意URL。
- [ ] 接已有受限PG夹具，经普通Node service→HTTP保存→重读→第二版CAS→旧版冲突→原请求恢复；合成来源不证明真实平台。

## Task 2: 编辑器版本恢复（UI agent）

Files: `pages/outreach/ContactEditor.tsx`, `useContactDraftSave.ts`，必要新增本目录专属hook，`desktop/tests/ui/contact-draft-persistence.test.tsx`。

- [ ] RED：重开恢复正文/版本/账号/对象与下一保存前驱，comment/dm独立；迟到读取不覆盖输入；核对UNKNOWN只用原request；失败读取挡保存且可重试；账户/来源切换丢弃迟到结果。
- [ ] 最新草稿读取只在非sample且service.latest可用时；本机有改动先保留，显式按钮采用云端稿；加载失败不以初始版本覆盖。保留本机编辑所用前驱，不静默在发送时更新。
- [ ] 成功保存/恢复时更新对应channel前驱；version至少已保存version，新修改版本严格更高；accountId/recipient变化也算本机修改。旧保存确认不能清除后来文字或旧发送确认。
- [ ] 传入 `save({...input,previousRequestId})`，onSaved同时传receipt.binding（legacy兼容可选）。新source/profile下的历史稿只可显式采用正文后重新核对，不能自动带入旧授权。
- [ ] 不改共享service/domain/root文件；定向UI测试；追加提交，禁止amend/push。报告独立文件。

## Task 3: 集成（Root＋独立review）

- [ ] 改动相关测试、类型、一次renderer构建；逐项说明真实与合成边界。
- [ ] 整批独立代码/架构/质量审核，修复后仅差量复核。
- [ ] 更新本记录与任务书简短入口，fetch后正常推送 `HEAD:main`，不强推、不改其他工作区。
