# P14/P15 与造包测试最终独立代码复核

候选：`f18a922b778f437400de8165e67b162fea028724`；基线：`0b05e98926e7e18858f0ab8e5780e49a3500ab4c`。范围为两者之间 12 文件，包含 `90d06d1` 的空间隔离、`4954534` 的存储收尾、`5d9476f` 的 ASAR 测试等待以及最终 legacy 成功分支修复。

**结论：此范围代码/架构复核 PASS。已报告的空间与存储问题关闭，未发现剩余 P0/P1 或需阻止本候选构包的具体缺陷。** 可进入绑定本提交的最终构包与可见验收；此结论不等同于发行签名、Windows 安装或后台能力已接通。

## 收口核对

- 完整 service、认证、userId、accountScope ID/版本作为 P14 工作区 remount 与请求代次边界；P15 本机表单键按相同身份隔离。旧页面、弹窗、正文以及迟到写入/核对响应不跨空间消费。
- v2 原请求 envelope 的 owner/key/binding 写入并回读之后才派发；无归属的旧用户级记录不自动认领，同空间旧版本保留可见请求 ID 与阻断。首次进入 P14 之前，全局清草稿也保留旧 session-only 跟进锁。
- 成功收尾先可靠写入并回读提交稿 key/hash ACK，再发布到会话内存并删除精确 durable 原锁。ACK 抛错、静默不写和读取失败不会放行新请求。清理正文之后，再确认原正文确已从 storage 消失，才能消费其 ACK；正文删除失败保留 ACK，避免刷新复活可再次提交的旧稿。原稿被人工修改和确定 FAILED 的情况保留输入。
- legacy `addFollowup` 的确定成功返回现在也调用相同 `finishConfirmed`，没有创造结构化回执。后续本机 ACK/清锁失败时，文案明确“接口已返回成功、本机确认失败”，保留原保护并要求人工核对已有登记。旧 facade 没有原 requestId 查询能力，未知状态不会自动重发。
- API 的输入绑定、预检、原记录保留和成功回执校验未被弱化；没有新后台实现或真实外发行为。

## 已知问题与证据链

此前 `90d06d1` 独立六套 49 passed 不能覆盖存储故障，预审保留于 `/tmp/yike-followup-code-90d06d1.md`。本审核者对 `4954534` 单独构造并运行 legacy 确定成功＋正文删除失败反例，确认为 **1 failed / 12 skipped**，日志 `/tmp/yike-followup-legacy-ack-red-4954534.log`。当前生产修复由另一代理完成；该反例纳入最终回归后通过。

最终本审核者独立运行：

```text
node node_modules/vitest/vitest.mjs run \
  tests/ui/followup-scope.test.tsx \
  tests/ui/followup-operation-storage.test.ts \
  tests/ui/followup-completion.test.tsx \
  tests/ui/followup-routing.test.tsx \
  tests/ui/followups.test.tsx \
  tests/ui/followup-ledger.test.tsx \
  tests/ui/hooks.test.tsx \
  tests/ui/operation-ledger.test.tsx
```

Node 24.19，**8 文件、89 passed、0 failed、exit 0**，2.53 秒。日志 `/tmp/yike-followup-code-f18a922-tests.log`。工作树 tracked 文件与提交一致；四个 raw-candidate 草稿、QA 目录未跟踪且不纳入候选。

## 两个 ASAR 测试文件的非作者审核

`packagedSmoke.test.mjs` 与 `verifyPackage.test.mjs` 共三个 fixture 创建点增加 `await finished(await asar.createPackage(...))`。已核实锁定的 `@electron/asar 3.4.1`：`disk.js` 的 `writeFileListToStream` 返回 `out.end()`，其 WriteStream 通过 writeFilesystem/createPackage 返回，但 Promise resolve 不保证写入 finish。原先随后立即 spawnSync 会阻塞宿主写流继续落盘，负例可能误读未完成的 JSON。

该修改在启动读取进程之前等待流完成，并传播写流错误；没有修改产品实现，也没有放宽任何坏包/空 preload/渲染失败拒绝断言。此窄改独立只读 PASS；专项 21/21 由 root 执行，本审核者未冒称独立复跑。原完整测试失败日志必须保留，后续全量结果另绑定最终候选。

## 验证限制

没有重跑全套前端/Windows/PG；没有使用 TEST 内存成功作为真实客户保存或消息回流证据。结构化 followup 后台仍是可选接入，legacy 原请求查询缺口在合同中保留。a25 旧中间包不覆盖此提交，最终包需重新核对源码、ASAR/ZIP 与可见原生结果。

## 后续测试窄修与最终生产字节绑定

最新候选 `c59cf1b68d5446be6a4fbb2ea9d6e9815f1a349e`，中间正常合并 `07d4b85` 的远端增量未改 desktop；本审核者没有在此重审这些后端/文档内容。相对 f18a922 的唯一 desktop 差异为 `tests/ui/followup-completion.test.tsx`。

该测试在 mutate fixture 被真正调用时释放 requestStarted Promise；先等待真实异步 SHA-256 与预检完成，再推进假时钟 30,001 ms。mutate 仍返回永不结束的 Promise，调用一次、超时提示、原锁保留和草稿保留断言原样。它没有缩短产品计时或绕过任何预检。独立窄复核 PASS；实际单用例 **1 passed / 23 not selected**，日志 `/tmp/yike-followup-timeout-code-c59cf1b.log`，未当作完整套件通过。

`final/release-desktop-equivalence.json` 逐字节确认：f18a922 构包对应 c59cf1b 的全部 177 个生产/打包输入（desktop 中排除 tests/docs，其余含源代码、资源、config、lockfiles）未变化。构建前后全部 317 个 tracked desktop 文件曾与 f18a922 精确一致；后续单测试改动已明确分开，未把不同树悄悄当作同一构包来源。

## c88c9e2 管理用例等待与最终全量观察

候选 `c88c9e20934c536a600d67dfe2ba2f7a02dd6404` 相对 c59cf1b 仅改 `tests/ui/management-scope.test.tsx`：先让真实会话初始化及空间 reset effects 结束，再开始选文件；释放 file.text 后等待“已选择”界面状态真正提交，再检查选择器已解除禁用。读取中禁用断言、选择文件文本及结束后启用断言仍保留，产品文件未改。独立只读窄审 PASS；相关单例实际 **1 passed / 3 not selected**，日志 `/tmp/yike-management-timeout-code-c88c9e2.log`。

root 的最终完整套件已完成且本审核者实际读取日志：`final/release-verified-tests.log` 为 **101 passed files / 1 skipped file；1121 passed / 22 skipped tests，1143 total**，12.78 秒；调用与源码清单绑定 c88c9e2。该结果是 root 执行、本审核者验证日志，不混同为本审核者再次全量运行。此前 ASAR fixture 和两个异步等待失败日志保留，没有删断言或将 skipped 计为通过。
