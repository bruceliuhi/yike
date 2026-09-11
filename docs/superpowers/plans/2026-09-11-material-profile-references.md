# 资料画像引用与失效闭环

> REQUIRED: subagent-driven-development；每批只做受影响验证及一次非作者整批审核，修复仅差量。复用当前隔离 worktree，不重跑全量基线。

**Goal:** 接通已批准的资料复用/撤销语义：新采用的资料字段有持久出处；撤销或修改资料后，新生成不再使用失效依据，原文字/任务/历史事实不删除。

**Architecture:** 画像版本与字段引用同事务保存，独立引用表保存最小资格、原始来源标识与采用值摘要；资料正文仍 owner-private。只在真正使用画像正文的搜索建议和候选 AI 判断处校验资格，不给无关采集/人工短句加封禁。现有复制的文字不追溯伪造出处。

**Tech Stack:** 原 PostgreSQL/RLS、Python facade/模型 worker、TypeScript 固定 IPC、现有 P03/P04，不增加模型/依赖/页面布局。

## Global Constraints

- 基线 `f336075d9f9575a5bc2f97af126c2508943568d5`；完整 V0.2 不缩减。无真实平台外发、模型调用或部署授权扩大。
- 资料仍私有；同租户其他用户仅通过最小引用资格继承已共享画像字段，不读取他人资料正文/名称/提取内容。跨租户不能读或继承。新来源必须是当前用户自己的 READY 精确版本与有证据的字段。
- 保存与引用同事务；引用来源参与画像内容去重，文字相同而来源不同不得错复用。资料变更不会自动替换来源，不自动 revoke 整个画像，不擦除人工文字/旧任务/已发事实。
- 取得原 MaterialStore owner advisory lock 在画像事务/行锁之前；不能反向等待。资料失效与引用资格失效同事务，影响 token 绑定实际引用快照，有新引用时须重新确认。
- 新生成前和采用结果前核对资格；正在执行的外部调用不能声称已撤回。原请求/调用事实保留，失效结果不得变成当前可采用建议。无资料引用的旧画像继续原行为。
- 前后台闭环完整后才接普通 UI，不把存储基础当用户功能完成。只定向测试、一次必要 HTTP/受限 PG 联验，一次整体独立审核；不构包，既有 Windows 候选保持原固定 SHA。

## Task 1 — 后端持久引用与两条模型边界

**Files:** 新 `pilot/material_references.py`、`migrations/132_v02_material_profile_references.sql`、`tests/test_material_profile_references.py`；修改 `pilot/store.py`、`pilot/ui_api.py`、`pilot/materials.py`、`pilot/search_suggestions.py`、`pilot/candidate_review.py` 及现有受限角色授权入口。仅这些后端路径。

**Interfaces:**

POST `/api/ui/profiles` 保留 description，新增可选 `baseProfileVersionId`、`materialReferences`（最多5项，字段唯一）。每项是严格二选一：

```json
{"field":"service","sourceProfileVersionId":"uuid","materialId":"id","materialVersion":4,"extractionId":"id"}
```

或继承当前已保存画像的引用：

```json
{"field":"service","referenceId":"uuid"}
```

继承必须同时提交 baseProfileVersionId，引用属于该版本、同租户且有效，目标字段采用值摘要仍一致；修改该字段不能悄悄冒用旧引用。手工修改时 UI 明确改为人工字段；原引用历史仍保留。新采用值允许人工编辑，服务端从规范 description 五字段编码解析/限长并计算 SHA256，不接受客户端提供可信摘要；对应资料字段须有原文证据。

保存/读取画像返回新增可选 `material_references: [{field, referenceId, valid}]`；无引用返回空数组。不得返回来源私密内容。保存结果仍原 version_id/version/status；普通 facade 列表与 confirm 读取须附最小引用元数据。

用独立 tenant-scoped 引用行记录目标画像/字段、来源owner/资料版本/提取ID、采用值摘要、有效资格；用户不能直接改 provenance。正文仍只在既有资料表。RLS/grants 限定源owner可使其资格失效，不能更换目标/来源或恢复旧资格；绑定与继承由服务事务校验。参考现有迁移125/131和授权规则，不使用 app 超级用户来证明安全。

- [ ] 写定向失败用例：READY引用保存/重开；同内容不同出处去重；跨租户/伪造字段/旧版本/非READY拒绝；继承允许共享最小资格但不泄露正文，修改采用值不能继承。
- [ ] 实现严格请求与原 save_profile 的同事务引用，引用规范身份参与 payload 摘要；确认引用失效画像须明确拒绝确认，但历史文字/状态不自动篡改。
- [ ] impact 返回真实 profile 影响（现契约 kind/label，最多100项；超出不可静默漏报），token 保存排序引用快照 SHA；remove/revoke 消费时重算。save 修改已 READY 内容也使相关引用失效。
- [ ] 搜索建议 preview/reserve/prepare_dispatch/finish，以及 CandidateReviewStore 的 ASSESS 预留/调用前/结果采用处检查当前资格。人工核验、采集执行和目前不读画像正文的 short coach 不加无关阻断。完成后失效保留调用/原请求事实，不返回可采用内容。
- [ ] 使用独立临时 PG（不得用或操作 shared yike-identity-contract-pg）；先 RED 后 GREEN，仅新增契约/生命周期/两条实际生成边界。模型用隔离合成响应，不外发客户信息。报告精确命令、结果、失败及未验边界，提交自己文件但不 push。

## Task 2 — 原画像页面与固定 IPC 接通（根代理）

**Files:** `desktop/src/renderer/pages/Profile.tsx`、`pages/profile/MaterialsWorkspace.tsx`、domain/models 与新 `shared/profileMaterialReferences.ts`、services/contracts.ts/client.ts、main/servicePolicy.ts，定向 adapter/UI 测试。

- [ ] 先写失败测试：采用READY字段后保存同时提交新引用；重开携带继承引用；手改字段明确解除该字段的待继承资格但保留文字；其他字段引用不丢；失效引用显示需重新采用而非READY。
- [ ] `onApply(fields, record)` 传原资料身份；ProfileEditor 按字段保存待提交引用与原字段快照。手改引用字段给可见“改为人工内容”提示；不得默默把失效来源当有效。旧本机草稿无引用保持原路径。
- [ ] 扩展 `saveProfile(fields, {baseProfileVersionId,materialReferences}?)` 与固定 IPC 严格 schema，拒绝重复字段/额外属性。API回执使用服务端引用而非本机猜测；迟到/切号/保存未知沿原保护。
- [ ] 保存不自动确认；引用失效时用户重新采用 READY 资料，或显式改为人工内容后另存画像。使用原 Notice 与字段提示，不新增页面。
- [ ] 只运行新增/受影响 adapter/UI 用例、类型检查；不重复全量或构包。

## Task 3 — 整合交付

- [ ] 一次普通HTTP→受限PG联验：保存/确认引用画像→生成前检查→撤销真实引用→下一次生成拒绝且旧文字/任务保留；修改影响窗口的新引用使旧token失效。
- [ ] 更新 UI_MATERIALS_CONTRACT 与 taskbook/整合状态，仅如实记录本批；独立非作者按整批源码审核，修复差量后 normal push main。
- [ ] 真实模型质量、Windows候选、平台与生产/UAT仍未验证，完整Goal保留。
