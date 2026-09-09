# P04 本机资料带入：独立架构与交互复核

- 候选：`d66d487a0f731d917ea65aeb2d6af51536e6cf10`。
- 原缺陷基线：`a08751d0b02d21c7d70b08f24eaaac2ca73bec8a`。
- 仓库：`/Users/bruce/Developer/work/yike-ai-product-design`。
- 结论：**本次 P04 增量 PASS，限定范围内无剩余 P0/P1/P2。**
- 产品实现由主线程编写；本审核人未修改该产品实现，独立编写失败回归及边界回归。2026-09-10 复核时，以下 8 个源码/测试文件相对候选没有未提交差异；9 文件提交中的资料合同增量也已阅读。

## 审核范围

`Profile.tsx`、`profile/LocalMaterialDrafts.tsx`、`profile/MaterialEditor.tsx`、`profile/MaterialsWorkspace.tsx`、`profile/localMaterialIdentity.ts`、`profile/profile.css`，以及两份新增测试和 `docs/UI_MATERIALS_CONTRACT.md`。未扩大至其他页面、后端、平台执行或 Windows。

确认的行为：

1. 首个服务端画像保存后，原本机资料仍可查看、编辑和删除，不因客户资料工作区启用而隐藏。
2. “带入当前画像”只预填资料编辑器；取消不调用 mutation，人工再次保存才同步，原本机草稿保持保留，内部引用范围不自动提升，也不自动解析或确认。
3. 同一用户、空间 ID/版本、画像版本 ID、本机资料 ID 使用带版本前缀的 JSON 元组计算 SHA-256 目标 ID。既有同目标记录携带其 `expectedVersion` 编辑，不另造对象；稳定 ID 本身不构成权限证明。
4. 已存在不同正文的客户资料在预填后取消，原正文与引用范围保持不变。正在解析的同目标资料拒绝带入；待核对、读取错误、容量限制沿用现有保护。
5. 实际 SHA 运算已完成但交付被延迟时，同用户切换空间 ID 或空间版本会卸载原编辑边界；迟到结果不打开新空间中的旧预填面板，不触发 mutation。
6. 最后 `safeParse` 增量保留校验语义，非法资料给出固定中文提示，不直接暴露 Zod 结构错误。

## 实际证据

### 真实缺陷 RED

日志：`/tmp/yike-material-local-handoff-red-20260910.log`。

在原产品源码上，真实 `AppProvider` 驱动无画像 → 本机资料保存 → 首个画像保存 → 回资料页。结果为 **1 failed**，精确失败在 `material-local-handoff.test.tsx:122`：找不到此前已保存的 `TEST 首次准备的案例`。失败之前已确认没有调用资料 mutation。这是产品入口丢失反例，不是依赖或测试准备错误。

### 最终独立 GREEN

运行目录：`/Users/bruce/Developer/work/yike-ai-product-design/desktop`；Node 24.19.0。

```sh
PATH=/Users/bruce/.nvm/versions/node/v24.19.0/bin:$PATH node node_modules/vitest/vitest.mjs run tests/ui/material-local-transfer-boundaries.test.tsx tests/ui/material-local-handoff.test.tsx tests/ui/profile.test.tsx tests/ui/profile-materials-integration.test.tsx tests/ui/profile-materials.test.tsx --reporter=dot
```

日志：`/tmp/yike-material-local-independent-final-20260910.log`，**5 files / 40 passed**。此数包含原有资料套件和新增 5 项，不与此前 4 files / 36 passed 相加。

- `material-local-handoff.test.tsx`：完整人工带入流程，包含编辑、本机保存不写服务、预填取消、人工保存、引用范围、重复带入目标 ID 和版本。
- `material-local-transfer-boundaries.test.tsx`：4 项，涵盖既有远端正文/引用范围取消保护、解析中拒绝、同用户空间 ID 与版本切换后的真实 SHA 迟到保护。SHA 使用真实实现与实际字节，仅延迟结果交付。
- Typecheck：`/tmp/yike-material-local-independent-typecheck-20260910.log`，退出码 0。
- `git diff --check`：通过。

### 测试准备问题的准确区分

首次新增边界测试运行曾为 1 failed / 4 passed：测试在列表仍 loading、按钮 disabled 时直接点击，因此未打开编辑窗；这不是产品反例。已改成等待按钮真实可点击后再触发。同期测试 fixture 的 `purpose` 类型过宽也已在测试中收紧。日志保留在 `/tmp/yike-material-local-independent-boundaries-20260910.log`，最终 40 项和类型检查均已覆盖修正后的测试；没有通过修改产品行为或伪造 hash 来绕过失败。

## 限制及合并边界

- 可选 `MaterialService` 在这些测试中由明确 TEST 隔离适配器提供；未新增或验证生产资料 HTTP/IPC、数据库、真实上传、AI 解析与引用追踪。
- 客户资料 ID 唯一性、权限和 `expectedVersion` 原子校验仍属于真实服务端接入要求。未执行 PostgreSQL 或外部平台请求。
- 本次未进行原生可见验收、打包或 Windows 测试，不代表整个 UI Goal 或 R4 完成。
- 未来远端合并须另绑定准确 merge SHA；本报告尚未为 `bbe2e20` 及其详情 `source_evidence` / `AbortSignal` 接入、执行准备或 P14 集成做验收。
