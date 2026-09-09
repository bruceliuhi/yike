# a25ba7b 限定集成质量核对

- 候选：`a25ba7b331e7712c4fba53b173cbbc704ec3e734`。
- 父提交：`1c56fc5734c738558067979c99c2fdd23d307552`。
- 仓库：`/Users/bruce/Developer/work/yike-ai-product-design`。
- 判定：**本轮已审切片的源码集成限定 PASS，未发现新增 P0/P1 阻断。** 新候选完整 gate、Mac 包及实际可见验收仍待主线程产出后独立核对；此结论不代表整个前端 Goal、Windows 或生产服务验收完成。

## 范围与作者隔离

本次只读核对该提交的 27 个文件、与已审切片的对应关系、测试时间边界及测试入口接线；没有改产品源码、重跑全量测试、构包或操作 UI。

1. P04：画像/资料编辑状态按可信会话空间隔离；资料原请求保存 v2 身份封套，旧版本/缺归属记录保守阻塞，迟到结果不应用到新空间。最后点号 ID 修正限定于 `materialOperationStorage.ts` 与其测试：前后缀只用于扫描，完整封套/key 校验后还精确比较 user/profile，避免合法点号 ID 被误归属。Peirce 作者报告四套 45 passed；Popper 非作者原范围 43 passed、最后 storage 增量 10 passed，不能将这些重叠数字相加。
2. P12/P13：本审核者已独立审查 `Outreach.tsx`、`outreach/ContactEditor.tsx` 及三套回归，并实际运行 **3 文件 72 passed**。证据版本进入发送条件指纹；两种用途的未保存编辑共同保持退出保护；仅原请求可信终态清除对应发送错误，未知/错请求及其他核验错误不被清除。未改发送授权或后端回执协议。
3. TaskWizard：平台状态的显式可访问名称与可见文案使用同一状态值，历史无 research 草稿保留纯平台名；测试覆盖加载到失败、实际连接状态、空间切换后迟到结果和历史草稿。该切片由 Peirce 实现、根代理非作者审查。本次阅读候选差异未发现额外业务变更。
4. P18 TEST management 恢复夹具、控制器、模拟 saveExport 和相应测试是**本审核者作者范围，不自批其实现**。采用 Popper 独立只读结论：3 文件 15 passed，无 P0/P1/P2；范围仅固定 TEST 空间的纯内存恢复、原请求查询/取消和模拟保存回执，未声称多租户授权、写盘或真实管理服务接通。
5. 根代理 P04 TEST 暂扣回执夹具及 main/README 接线：本次独立阅读。P04/P18 恢复场景显式 opt-in，限定相应页、populated 和 TEST 登录态；控制器只改变内存回执可见性或下一次结果，产品页仍须发起原请求查询/取消。默认不注入 native bridge；P18 仅注入模拟 saveExport。TEST 提示和 HMR 重置边界已写清。

Popper 随后精确绑定同一候选的独立报告 `/tmp/yike-ui-state-architecture-a25ba7b.md`，确认其 P04/点号差量、TaskWizard、TEST 材料、P18/接线范围无剩余 P0/P1/P2；其独立记录分别为 P04 原四套 43、storage 差量 10、P18 三套 15、TEST 材料一套 3，数字有重叠，不相加。本报告没有把该审核者自己编写的 Outreach 当作其独立结论。

## 实际核对证据

- `git rev-parse HEAD`、`git diff-tree --no-commit-id --name-only -r HEAD`：候选确为上述完整 SHA，共 27 个文件。
- 对这 27 个文件逐项比较 `git show <SHA>:<path>` 与工作树 SHA-256：**0 项不同**。`git diff --name-only HEAD -- desktop` 为空；没有额外已跟踪源码改动。
- `git diff HEAD^ HEAD --check`：通过。
- `git ls-tree -r --name-only HEAD -- <四个 raw 路径>`：无条目。以下仍是未跟踪草稿，没有进入候选：
  - `desktop/src/renderer/domain/rawCandidates.ts`
  - `desktop/src/renderer/services/rawCandidates.ts`
  - `desktop/src/shared/rawCandidateRead.ts`
  - `desktop/tests/rawCandidateReads.test.ts`
- `git grep` 检查候选生产 `desktop/src`、Forge 与 production renderer config 中的上述 raw 名称及 visual 恢复夹具引用：无匹配。visual 的独立入口/输出目录仍与 production renderer 分离；此静态核对不替代新 ASAR 的排除检查。
- README 本地 Markdown 链接存在性检查：0 个缺失。
- 本审核者此前独立触达命令：`PATH=/Users/bruce/.nvm/versions/node/v24.19.0/bin:$PATH npx vitest run tests/ui/outreach.test.tsx tests/ui/outreach-reconciliation.test.tsx tests/ui/send-confirmation.test.tsx`（工作目录 `desktop`），**72 passed**，日志 `/tmp/yike-outreach-increment-review.log`。本次候选中对应源码/测试仍是该冻结内容，没有重复运行。
- P18 作者自测日志 `/tmp/yike-p18-management-tests.log` 为 15 passed，`/tmp/yike-p18-management-typecheck.log` 为 typecheck 通过；它们只作为作者验证记录，非本审核者独立放行依据。

## 全量和产物时间边界

`docs/qa/ui-state-recovery/source-before.json` 的 296 项输入与候选比较，仅 `materialOperationStorage.ts` 和 `material-operation-storage.test.ts` 不同，恰为最后点号 ID 修正。该 snapshot 对应 `logs/tracked-tests.log` 的 **92 文件、1005 passed / 21 skipped**，因此**不能记成 a25ba7b 的最终全量结果**。45 项定向是最后修订的作者验证，不代替最终完整 gate，也不与旧全量相加。

截至本报告，未核对 a25ba7b 的新 ZIP、ASAR、逐输入清单或原生截图；历史包和历史可见链不能绑定为新候选。待主线程提供新证据后再做产物字节绑定与实际 UI 范围核对。TEST 保存回执不等于原生文件选择器，纯内存恢复不等于真实后端恢复，Windows 仍以用户实机脚本和证据为准。

## 后续证据增量：最终测试与 P18 静态记录

主线程最终 `docs/qa/ui-state-recovery/logs/final-tests.log` 已完成，实际日志为 **92 文件、1007 passed / 21 skipped**。`source-final-before.json` 声明上述 a25 完整 SHA，本审核者逐项比较其中 296 项与提交字节，0 项不符。本次仅核对日志和输入，没有重复全量运行。

P18 的运行静态 freeze 在最后 P04 两文件点号修正之前；重建前已保存 `docs/qa/ui-state-recovery/p18/build-binding.json`，37 文件完整哈希和 Vite manifest。这是事后原文件采集，不是补造运行前哈希，capture HEAD 也不等于其构建源码提交。P18 实现切片在两个 snapshot 间不变，不把该事实扩大成完整 a25 构建证明。

`p18/README.md` 已记录事件与 AX/图像适用范围：恢复原请求执行一次、查询两次；TEST 下载执行一次、取消 PENDING/CANCELLED 各一次；三个独立导出分别取消/模拟保存/失败。旧放大裁切的 export-cancelled PNG 不作完整布局证据；预览及待确认下方控件以 AX 补充，未宣称一屏全部可见。仍待新生产包及原生证据后核对产物绑定。

## 后续已知限制与中间包

后续检查另发现 P14/P15 跨客户空间 P1，超出前述本轮 27 文件切片的独立结论，正在单独修复。因此 a25 不作为最终交付候选；不能用本报告初始限定 PASS 关闭该 P1 或整体 Goal。

已独立核对 a25 中间包，详见同目录归档 `yike-ui-state-artifact-a25ba7b.md`：296 源输入前后/提交一致，实际 ZIP/ASAR 与记录相符，37 个 renderer 文件和三项 main/preload/manifest 哈希均通过。ASAR 为 `dbb50b11feb25e35b4d5055af106022fd64a7d71a6ff3c9e7d7f9c1556eea582`，ZIP 为 `f557ec55424b875df6b56f5e5de664a17b71dc2f24375c1947d6446651771806`。结论仅为中间产物完整性，不含后续修复和可见原生 UAT。

P04/P12 静态 CUA 证据已整理：资料撤销/移除原请求各执行一次、重入仍保护；P12 保存评论一次后私信仍保留退出保护，并有最终到达工作台 AX。P04 追加的人工提取应用仅替换所选服务字段，其它原 TEST 字段保留，页面仍明确未保存；没有新画像保存/确认事件。旧通知短暂并存和同画像标签额外离页确认列为体验观察，不误判为长期失败或数据丢失。

补充校正：上述可见验收实际使用 Codex In-app Browser（IAB，browser2）/CUA。已核对 context.tsx 的通知在 6000ms 后按 ID 自动移除；P04 终态瞬间旧/新通知并存是非阻断体验观察，不是永久残留或已确诊故障。
