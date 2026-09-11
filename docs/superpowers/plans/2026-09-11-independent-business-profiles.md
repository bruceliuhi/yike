# 独立业务画像 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. 按已批准完整 V02 业务理解项实施，不新增一级页面。

**Goal:** 同一客户空间的不同产品/客群独立建档、独立确认，原任务继续绑定原版本。

**Architecture:** 复用 business_profiles 实体和 business_profile_versions 版本表。新增业务使用稳定请求 ID 创建；编辑明确传实体 ID，省略时保留旧默认业务接口。原页面添加新建入口与名称，不重做布局。

**Tech Stack:** Python/PostgreSQL、普通 HTTP/IPC 服务、React/TypeScript。

## Global Constraints

- “不同业务能独立建档；不靠替换行业标签；资料缺失不编造，更新不覆盖已确认任务。”
- 租户由认证身份解析；引用继承不得跨业务版本，显式重新采用资料仍按既有资格检查。
- 首次创建重试复用同一业务；新建清空引用，脏草稿切换需要确认；迟到回执不能覆盖新编辑。
- 不改变实际发送、价格、生产部署权限。只做变更路径测试及一次独立整批审核，不构包或重跑全套。

### Task 1: 后端实体选择与兼容

**Files:** pilot/store.py、pilot/ui_api.py；tests/test_independent_profiles.py。

**Interfaces:** POST /api/ui/profiles 在旧 description/baseProfileVersionId/materialReferences 外支持互斥可选 `profileEntityId` 或 `newBusiness:{requestId,name}`。实体 ID 接受已有32位小写hex/UUID；requestId规范UUID；name去首尾空白后1–100字符、无控制字符。newBusiness实体由 tenant+requestId 确定，不接受任意跨租户ID创建。已有实体不存在失败，不回退默认。重复创建请求名称变化失败。回执/list/get 均提供 profile_id、profile_name；其它已有字段不变。

- [x] RED：新增PG定向案例先验证新建两个同内容业务ID不同且均CONFIRMED；业务A新版本确认仅撤销A旧版；B与A旧任务保留。
- [x] 实现 `save_profile(..., profile_entity_id=None, new_business=None)`，在既有资料锁之后取正确实体行锁。确认逻辑复用原实体作用域。继承base版本须属于当前实体。旧省略参数行为保持。
- [x] 验证创建重试稳定、名字变化/跨租户/未知实体/错业务base均拒绝；最新列表与确认回执保留实体名称。使用独立PG，少量新用例，不跑旧全量。
- [x] 提交仅后端与新测试；报告记录命令与证据边界，不push/amend。

### Task 2: 普通客户端与原画像页

**Files:** desktop/src/shared/profileMaterialReferences.ts、renderer/domain/models.ts、services/client.ts、pages/Profile.tsx；desktop/tests/ui/independent-profiles.test.tsx。

**Interfaces:** 扩展现有saveProfile第二参数为上述互斥选择；Profile新增可选businessName，profileEntityId仍指实体，id仍指版本。

- [x] RED：原页选择A后编辑提交A实体；新建清空字段/引用、保存带稳定newBusiness请求；取消脏草稿切换保留内容。
- [x] 复用页顶按钮/版本选择器，选项显示业务名称+版本；新建显示名称输入。LocalDraft保留newBusiness/requestId。旧无entity响应兼容但新显式选择缺失/不符回执失败。
- [x] 保存快照包含实体/新建身份及名称；提交未知时保留原请求，切换/修改后的迟到结果不覆盖。新建清空资料引用；当前业务修改与资料引用保持原逻辑。
- [x] 定向UI/客户端测试、一次typecheck；独立整批审核通过，按原授权整合main，不重复测试。

## 实施与验证

基线 `bce3022`；后端 `004239f`、客户端 `f193453`、普通HTTP测试 `c16a8c8`、受限角色资格 `077f68a`。既有数据库表已支持实体/版本，本批无迁移、无新增服务。

- 原画像页“新建业务画像”→填写名称与内容→保存→确认；也可选择既有具名业务修改。任务/评估选择器继续提交版本ID，显示业务名称。
- 创建请求ID随本机草稿保存；重试复用实体，名称冲突明确失败。确认只撤销同业务原版本，旧任务不迁移；显式选择不存在或跨租户实体拒绝，继承base必须同业务。
- 前端新增4项先RED后 `4 passed`（2.45秒）；直接受影响的资料引用编辑/客户端 `6 passed`（2.40秒）；TypeScript检查通过。
- 后端新增4项先RED，再含普通HTTP共 `5 passed`（1.30秒）。HTTP随后改用受限角色，首次测试夹具遗漏版本表SELECT失败，补齐夹具后仅该项 `1 passed`（0.75秒）；实际使用 `NOSUPERUSER NOBYPASSRLS`，不是管理员冒充普通客户。
- 独立整批审核绑定 `077f68a`，结论GO，无Critical/Important/可执行Minor。不重复全套、Node链路、构包。上述为本地PG/HTTP和UI测试，不是真实平台、Windows实机、生产或客户UAT证据；完整V02仍进行中。
