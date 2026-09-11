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

### 实际联验发现

普通商机详情缺少旧式顶层证据version/time，现仅在旧字段缺失时从已验证CAPTURED快照取值，不升级sourceStatus。真实纳入流程另遗失来源健康状态：已确认OPEN的来源经通用导入仍为UNVERIFIED，使后端草稿拒绝全部新纳入机会。修复限定在 `_decide(INCLUDE)` 的新建分支，已有严格同版本核验和人工确认后才将UNVERIFIED初态写为OPEN；不改显式负面健康、不复活旧纳入，不放宽草稿门禁或修改通用导入可信度。沿用现有列授权，无新迁移。

## 实施与验证

源码：`d628957` 编辑器恢复，`5509232` 高版本UNKNOWN恢复，`2aef610` 普通传输及真实纳入接续，`fbc13a3` 阻止无修改重复保存。最终源码 `fbc13a3a82955896d5416af8f811b87fe7a4b25a`。

- 可验收入口：触达中心→评论/私信草稿。重开可恢复本人已存稿；已有本机文字时明确采用；保存中继续编辑会保留新文字；恢复高版本后不会用低版本覆盖。未修改的已保存稿不重复提交。
- Root定向四文件64项通过：`contactDraftService`、`ui/client`、`ui/r4-short-coach-domain`、`servicePolicy`。UI初批四文件80项，版本恢复差量两文件38项，最后冗余保存差量单文件8项；重叠集合不相加。
- `pytest -q --tb=short tests/test_desktop_contact_drafts_postgres.py`：1项通过/3.68秒，内部普通Node客户端实跑1项不跳过；覆盖同版本人工纳入→认证HTTP→受限PG保存/重读、第二次保存响应丢失→原请求恢复、旧窗口CAS拒绝、原回执保留、同租户其他用户不可读、退出拒绝。数据库实际仅两版草稿；重复纳入不复活后来BLOCKED的来源。现有原文捕获回归另1项通过。
- 类型检查通过；一次renderer构建470ms通过，绑定最终冗余保存按钮差量之前的产品代码。该按钮差量由8项定向检查覆盖，未重复构包；未形成新的桌面安装包。
- 原失败保留：缺失详情证据version；已核验新纳入机会仍停留UNVERIFIED；首次联验夹具未采用原研究稿savedContent；SQL计数未设置owner RLS范围及夹具清理顺序。前两项修复产品接线，后两项仅修测试；不绕过草稿校验。只有测试结束后按本测试tenant/opportunity清理合成草稿时，事务性暂停该表不可变触发器；所有验收读写保持受限角色/RLS/触发器。

独立代码/架构/质量整批审核＋最后差量复核 **GO**，绑定上述最终源码，无未关闭Critical/Important/Minor；复用定向证据，未重复全套。来源、模型结果和账号均为合成测试输入；真实平台/Windows/生产/UAT不据此完成。短句模型未接通，原请求缺失/HTTP冲突仍须后台确认，不承诺所有失败可自动解锁。完整V0.2 Goal继续推进。
