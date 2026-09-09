# 隔离视觉验收入口

此目录仅用于以测试状态运行真实 React 页面。入口复用生产 `App`、`AppProvider`、页面组件和 `YikeService` 类型，不改生产 main / renderer 入口。

P12 的待确认、待回复、需处理三个队列提供 TEST 内存状态供点击核对；沿用 populated/empty/error/loading 切换。默认发送仍拦截；显式 `recovery` 场景仅在内存中记录 TEST 请求并返回 UNKNOWN 或确定未执行，不模拟渠道投递成功。

**TEST 数据不是客户、商机业绩、真实账号或真实运行结果。** 内存中出现的“运行中”“已回复”等状态仅用于检查布局和交互。该工具不能证明真实采集、平台登录、发送或客户数据库接入已经完成。

## 启动与入口

在 `desktop` 目录使用 Node 24：

```sh
npx vite --config vite.visual.config.ts
```

仅监听 `127.0.0.1:18794`，端口被占用时退出，不自动换端口。不配置 API proxy，不读取业务服务地址或凭据。

- [P09 监控详情](http://127.0.0.1:18794/?scenario=P09)
- [P05 采集任务](http://127.0.0.1:18794/?scenario=P05)
- [P08 监控列表](http://127.0.0.1:18794/?scenario=P08)
- [P14 跟进记录](http://127.0.0.1:18794/?scenario=P14)
- [P15 添加跟进](http://127.0.0.1:18794/?scenario=P15)

可将 `scenario` 替换为 `P01` 至 `P20`。也支持首次打开 `http://127.0.0.1:18794/#P09` 或 `#/P09`，会转换成对应语义路由；页面内跳转继续使用真实路由。左下角 TEST 场景选择器切换页面时重新加载并重置内存。

`state=populated|empty|error|loading` 控制数据读取状态，默认 `populated`；详情在 `empty` 时呈现记录不存在。会话默认使用 TEST 身份，`session=guest` 或 P01 使用访客。启动确认仍缺真实账号和执行设备，不能启动；P13 仍禁止发送。

两个附加参数也只影响隔离 TEST 状态：

- `reference=r3`：按 [reference.ts](reference.ts) 将指定页面对齐到已批准 R3 的可比状态，例如画像草稿、未启动任务、监控平台状态和空跟进列表。`error` / `loading` 时不覆盖失败或等待状态。它不会修改生产数据或把参考图里的状态当成真实执行结果。
- `capabilities=complete`：仅在 `state=populated` 时挂接 [materials.ts](materials.ts) 和 [followup.ts](followup.ts) 两个可选 **纯内存 TEST 服务**。资料可进行保存、解析状态、人工确认和引用影响操作；跟进可新增、纠正、撤销、标已读和按原请求查询。这里的 `complete` 是测试入口参数名，不表示生产能力全部接通，也不启用真实采集或消息发送。与 `reference=r3` 同时使用时，这两个内存服务替换相应的参考空态服务。

例如 [TEST 跟进操作](http://127.0.0.1:18794/?scenario=P15&state=populated&reference=r3&capabilities=complete) 或 [TEST 资料操作](http://127.0.0.1:18794/?scenario=P04&state=populated&capabilities=complete)。所有输入应使用 TEST 合成内容；切换场景或刷新重建服务后内存记录重置。

P07/P10/P11/P12/P13 的 `reference=r3` 还通过 [routing.ts](routing.ts) 进入产品已有的 **公开样例** 路由；P12/P13 固定评论用途，P13 继续不可发送。没有 `reference=r3` 时仍显示独立 TEST 客户。`error` / `loading` 或显式恢复场景不会被换成只读样例，以免错误被成功样例掩盖。

## 有界恢复场景

[recovery.ts](recovery.ts) 复用真实页面与现有服务契约，四个名字严格限制对应页面、`state=populated` 和 TEST 登录身份；未知名字、错误页码、guest、error/loading 组合会明确拒绝启动场景。**这些不是已接通的生产能力。** TEST 账号、执行条件和核验 token 均是内存夹具；所有请求没有外部副作用，不发送短信、不打开真实平台窗口、不运行执行器、不投递消息、不写客户库。`reference=r3` 可同时存在，但不会把恢复场景改为公开样例。

左下角展开“TEST 场景”可见独立的恢复控制。按钮只改变测试服务的内存结果；解除产品页面上的原请求保护仍需用户点击产品的“核对原…结果”。未执行终态只有在本实例已经记录原请求后才可注入，不接受任意外部请求编号。每次演练只记录一个原发送/启动请求，核对确定未执行即结束本次；再演练需重新打开该场景。刷新页面重置整组 TEST 状态，不能将刷新当作生产锁恢复证据。

| 入口 | 可复现操作与可验证内容 |
|---|---|
| [P06 建议迟到](http://127.0.0.1:18794/?scenario=P06&recovery=ai-late) | 页面开始等待 TEST 建议；在关键词里“添加”`TEST 人工保留词`，展开左下角控制，点击“TEST 返回等待中的 AI 建议”。出现真实“更新搜索建议”确认，先检查人工词仍在，再选择“合并新增建议”或“保留当前”。也可先“取消生成”后再返回 TEST 结果，验证旧响应不应用。生产 45 秒超时不改变，超时后可点生成建议开始下一次；截图操作应在本次等待窗口内完成。 |
| [P20 建议与日程保护](http://127.0.0.1:18794/?scenario=P20&recovery=ai-late) | 复用相同迟到过程；修改每日时刻或间隔/窗口，再合并建议，日程不得回退。初始 09:00/15:00 与 Asia/Shanghai 仍来自批准的 TEST 配置。 |
| [P13 发送未知](http://127.0.0.1:18794/?scenario=P13&recovery=send-unknown) | 先进入完整 TEST 草稿编辑器，等待账号读取后点“准备发送”，再“核验发送条件”、核对全文并勾选、“确认并发送”。测试服务只记录原请求并返回 UNKNOWN。点击“核对原发送结果”仍 UNKNOWN，不能再发；在 TEST 控制中“确认原请求未执行”后再次核对，才看到确定未送达，必须重新核验。不会出现 SENT。先打开编辑器是为了让真实连接读取完成后再建立确认快照，不绕过连接变化保护。 |
| [P19 启动未知](http://127.0.0.1:18794/?scenario=P19&recovery=start-unknown) | TEST 条件已满足但没有真实执行器；勾选最终配置后“确认并启动”，只记录原请求与精确配置摘要，返回 UNKNOWN。“核对原启动结果”仍保留保护；通过 TEST 控制确认原请求未执行，再核对后释放，草稿保留且需要重新确认。不会创建 ACCEPTED 任务或显示真实运行记录。 |
| [P17 能力不足](http://127.0.0.1:18794/?scenario=P17&recovery=connection-limited) | 点击“打开登录窗口”仅推进 TEST 内存阶段，再“我已完成登录，检查连接”。返回带明确 TEST 名称的已连接状态，但能力列表为空，显示能力尚未验证；“完成并返回”通过真实 hash 路由回任务第二步 `step=connect`。不会打开平台原生页，不证明真实登录。 |

建议迟到、发送和启动原请求的参数绑定与页面行为分别由 `recovery.test.ts` / `recovery-pages.test.tsx` 覆盖；页面测试使用真实 `AppProvider`、异步 hashchange 与 StrictMode，没有同步路由 mock。原请求核对只接受本实例的精确 requestId、对象/用途/版本或配置摘要。发送终态只有 `FAILED + confirmed + confirmedNotDelivered`，启动终态只有 `REJECTED + confirmedNotStarted`；其他场景默认保护仍在，不能由样例解除。

20 个页面现在已有真实 React 运行截图与 R3 参考图的逐页对比。详细状态、可见流程、剩余差异与滚动限制以 [本轮 design-qa](../../../docs/qa/ui-flow-completion/design-qa.md) 为准，独立审核见 [QUALITY_REVIEW](../../../docs/qa/ui-flow-completion/QUALITY_REVIEW.md)。这不表示每页所有业务状态、所有分辨率、生产服务或 Windows 实机都已验收。

## 资料与管理恢复场景（2026-09-10）

- `?scenario=P04&state=populated&materials=recovery`：从产品页添加含 TEST 的资料，解析并人工确认后，在“TEST 场景”中选择下一次保存、撤销或移除回执暂为未知。必须先在产品页核对原操作；TEST 控制释放原回执后仍需再次核对，不能用刷新或新请求当作恢复。改变的是内存传输可见性，没有真实资料后台。该场景仅固定 TEST 画像，不证明跨客户空间授权。
- `?scenario=P18&state=populated&management=lifecycle`：TEST 控制选择模拟保存取消/成功/失败、执行或查询的未知/明确终态，以及取消待处理/已确认。恢复使用本目录 `TEST-management.yike-backup.json`，通过产品页文件选择和影响确认；只更改内存，不写文件、不恢复客户数据或安装软件。产品页正常请求与原请求查询仍由真实组件发起，控制器不直接清产品待确认锁。
- 并行开发的 HMR 会重置这些 TEST 内存。持续状态验收应先冻结独立 visual 构建，在相同 `127.0.0.1:18794` 入口提供静态资源并保留严格 CSP，再开始一条完整流程；不要把热更新重置当作产品操作结果。Windows 缩放和原生保存框仍另行验收。

## 数据与外部动作边界

05C确认接线的隔离入口：`?scenario=P19&strategy=confirm`（也支持P06/P20）。使用真实页面/控制器与[纯内存策略服务](strategy.ts)，可准备快照、主动确认、查询和撤销；新签名执行尚未接通，启动保持禁止。只有populated、TEST登录且没有recovery场景时启用；刷新后TEST回执/存储重置，不当真实恢复或PG验收。所有记录和来源均为TEST合成内容，保留外部动作隔离与生产排除检查。

- [fixtures.ts](fixtures.ts) 全部使用 TEST 标记。任务关键词、排除词和两次监控时刻沿用已批准的展台场景；不存在真实采购联系人、预算或成交数据。合成询价对象使用 `.invalid` 来源地址；产品自带公开研究样例仍按原页面的只读规则展示。
- [service.ts](service.ts) 数据每个实例独立深拷贝，画像 / 跟进 / 任务动作只影响该实例内存。候选入库、真实任务启动和消息发送始终不执行；默认启动/发送返回不可用，显式恢复适配仅返回上述 TEST 原请求状态。登录、短信、生成草稿等测试响应不调用外部服务。
- [materials.ts](materials.ts) 与 [followup.ts](followup.ts) 只接受固定 TEST 画像/商机范围，操作回执保存在各自实例的内存中。资料的解析内容和收到的回复均为测试内容，不调用真实 AI 或平台。它们不访问网络、客户库或持久存储，不属于生产 renderer 的依赖图。
- [isolation.ts](isolation.ts) 将 localStorage 与 sessionStorage 替换为内存对象，默认禁用 native bridge；仅上述 P18 场景注入只有 saveExport 的内存模拟桥。业务 fetch / XHR / beacon、剪贴板写入、外链打开和 CSV 下载（包括脱离 DOM 的下载链接）继续阻断。刷新后测试存储重置，不接触产品端口的存储。
- 页面固定显示 TEST 标识。外部动作只记录在 `window.__YIKE_VISUAL__.events` 的内存事件数组中；复制只记录字符数，登录不记录输入凭证。
- Vite 仅加载本机模块与 HMR，CSP 限制连接到本机入口；不应输入任何真实客户资料或凭据。

## 回归与生产排除检查

在 `desktop` 目录执行：

```sh
npx vitest run tests/visual
npm run typecheck
node tests/visual/verify-production-exclusion.mjs
```

排除脚本使用真实生产入口与 `vite.renderer.config.ts`，仅将输出改到 `desktop/out/visual-production-check`，检查构建模块图、产物文本和 Vite manifest 无 harness 引用。它同时检查当前磁盘存在的 Mac ASAR 的文件路径与内容标记；未找到包时输出 `existingAsarChecked: false`，不能据此宣称包检查通过。也可传入明确的 ASAR 路径作为第一个参数。

独立视觉构建若需要使用 `npx vite build --config vite.visual.config.ts`，输出到 `desktop/out/visual-harness`，不覆盖生产 `.vite/renderer`，且不是 Forge 的 renderer 入口。所有 `out` 产物不提交 Git。

当前记录见 [VALIDATION.json](VALIDATION.json)。后续修改生产打包配置或新建安装包时重新执行排除脚本；本轮对既有 ASAR 的检查不替代未来安装包检查。

完整前端回归使用 `npm test -- --run` 和 `npm run typecheck`，确切日期、测试总数及本轮限制记录在 [QUALITY_REVIEW](../../../docs/qa/ui-flow-completion/QUALITY_REVIEW.md)，不要将多轮重复执行的数量相加。

2026-09-09 19:28:32（Asia/Shanghai）恢复场景及公开样例路由增量验证：`vitest run tests/visual` 为 **6 文件、33 passed**，`npm run typecheck` 通过。生产排除检查返回 `productionGraphModules=4718`、`manifestHarnessReferences=0`、`existingAsarChecked=true`、`failures=[]`。这是当前工作树和当时已存在 ASAR 的隔离检查，不是新打安装包、真实通道或 Windows 验收；新增的 12 项恢复/路由测试已包含在 33 中，不再相加。
