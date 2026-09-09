# R4 独立质量复核：用量绑定与模板空间隔离

- 复核日期：2026-09-09（Asia/Shanghai）。
- 绑定提交：`190683c87af536b8e1af47e6a002abf0464d376b`，包含候选 `676970c` 与远端 `2ce6f8a` 的正常合并。
- 复核人：独立 Agent C。
- 判定：**本报告限定范围 PASS，未发现剩余 P0/P1 或需阻断交接的具体缺陷。** 此结论不等于全产品、截图、安装包或真实后台验收通过。

## 范围与独立性

本次只复核主线程编写的 R4 研究用量接入，以及 Agent A 收口的模板删除空间隔离。重新读取了目标提交对应代码与用量合同；以 `git diff --exit-code 190683c87af536b8e1af47e6a002abf0464d376b -- <复核文件>` 确认工作树中的这些文件与提交一致。

| 复核内容 | 入口与关键位置 |
| --- | --- |
| 用量配置、只读估算、绑定和有效期 | [researchUsage 域](../../../desktop/src/renderer/domain/researchUsage.ts)，第 126–215 行；[可选服务](../../../desktop/src/renderer/services/researchUsage.ts)；[useUsageQuote](../../../desktop/src/renderer/pages/tasks/useUsageQuote.ts)，第 17–105 行 |
| 客户界面的未知值及配置校验 | [ResearchSettings](../../../desktop/src/renderer/pages/tasks/ResearchSettings.tsx)；[用量交接合同](../../UI_RESEARCH_USAGE_CONTRACT.md) |
| 启动前核对与回执中的用量约束 | [TaskWizard](../../../desktop/src/renderer/pages/TaskWizard.tsx)，第 328–424 行；[taskOperations 域](../../../desktop/src/renderer/domain/taskOperations.ts)，第 207–237 行，仅本轮用量回执增量 |
| 旧请求跨空间核对和迟到保护 | [useTaskScope](../../../desktop/src/renderer/pages/tasks/useTaskScope.ts)；[PendingTaskStarts](../../../desktop/src/renderer/pages/tasks/PendingTaskStarts.tsx)，第 53–96 行，仅本轮空间与用量增量 |
| 模板删除弹窗及操作身份 | [useTaskTemplates](../../../desktop/src/renderer/pages/tasks/useTaskTemplates.tsx)，第 47–58、117–126、213–222 行；[回归](../../../desktop/tests/ui/task-templates.test.tsx)，第 182–214 行 |

**明确排除本人编写的 P12 短句教练、草稿保存和 CoveragePlan 实现，不以本报告自审批准这些模块。** 既有任务执行/核对底座也不因本轮增量复核而重新获得完整认证。

## 已核实的关键边界

1. **估算与实际执行分开。** `quote` 合同是只读；响应须精确匹配用户、客户空间 ID/版本、请求、草稿版本、配置摘要和上限，并包含计量规则、依据和有效期。未来生成时间、过期、缺字段或预计值超上限被拒绝。未估算显示“待估算”，未启动显示“尚未启动”，不会由空值推导零消耗。
2. **旧空间和旧配置不能借迟到结果继续启动。** 估算身份包含配置指纹、用户、认证状态、空间和服务实例；启动预检后及落锁前检查当前代次。带 `research` 的草稿必须有 `researchContractVersion=1` 执行适配和有效报价；旧执行器不能默默丢掉用量配置。历史无 `research` 草稿保留原能力路径，不宣称受新上限控制。
3. **UNKNOWN 不能作为失败释放保护。** 启动前先写入原请求及不含令牌的预留摘要。`ACCEPTED` 与 `REJECTED` 都须回显相同的 quote、规则、上限、客户空间；`REJECTED` 还必须明确 `confirmedNoUsageReserved:true`。失配回执保持原锁。恢复只查询原请求，带用量摘要的旧空间请求在其他空间不可查询；迟到核对不能解锁新空间界面。
4. **来源及本机草稿保持空间边界。** 相似研究和补查来源进入估算前复核用户及空间；本机任务、列表和模板使用空间 ID/版本分隔存储键。这里只批准用量请求与共享草稿接入点的校验，不扩展为对补查执行模块的自审结论。
5. **模板删除确认在渲染时隔离。** 删除目标与当时的 scope identity 一起保存；弹窗渲染和 `remove` 均核对身份，旧闭包另有 `scope.current()` 保护。回归故意在两个空间使用同一模板 ID，并在 passive cleanup 之前读取已提交 UI：切空间时旧确认窗已不显示，两个空间的模板都保留。

上述第 2、3 点覆盖此前指出的两项 P1：启动预检遗漏空间代次，以及终态回执/恢复查询遗漏用量与空间绑定。模板删除旧确认窗的窄 P2 已闭环。当前目标代码中未见这些问题再次出现。

## 本人实际执行的验证

在绑定提交的 `desktop` 目录，以配置的 Node 24 运行：

```sh
npm exec -- vitest run tests/ui/r4-research-usage.test.tsx tests/ui/task-templates.test.tsx
```

结果：**2 个文件、28 项通过，0 失败、0 跳过**；开始时间 `21:49:33`，耗时 `1.53s`，工具输出 `fd1c2d`。包含用量估算/回执失配、旧执行器拒绝、同用户换空间后的预检迟到、UNKNOWN 重挂载、来源空间校验及模板删除窄修。此前单独模板套件的 12 项通过与本次重叠，不能累加。

本次静态检查未在生产 `desktop/src`、renderer Vite 配置或 Forge 配置发现 `tests/visual`、`configureR4Visual` 或 R4 TEST 标识导入。只读核实 [生产 client](../../../desktop/src/renderer/services/client.ts) 和 [服务接口](../../../desktop/src/renderer/services/contracts.ts)：`researchUsage` 等是可选能力，生产 client 尚未提供真实研究用量适配，现有任务启动也明确返回不可用。

## 交付边界与待补证据

- [TEST R4 adapter](../../../desktop/tests/visual/r4.ts) 的估算、规则和账户空间仅用于隔离演练；TEST 返回值不能证明实际预留、扣减、释放、后台幂等事务或平台执行已接通。本次未进行真实外联、模型调用或扣费。
- 真实后台仍须实现可信账户授权、原子预留与任务创建、预算版本并发控制、幂等查询和资源结算，并提供服务端验证；前端的配置或 `confirmed` 字段不是服务端授权依据。售价、兑换比例、余额和退款均未由本轮定义。
- 主线程本轮完整测试、截图配对、原生启动、Mac 构建及包资源检查正在另行收口。**本报告此时未审阅它们的最终交付日志，不记录通过结论。** Windows 实机、生产平台能力和部署门禁也不在上述 28 项测试的证明范围。
- 本次仅新增此报告，未修改产品代码、提交或推送。后续交付证据应另行追加其实际源码 SHA、产物摘要和执行结果，不能沿用本报告的局部 PASS 替代。

## 最终 Mac 产物交付复核（追加）

2026-09-09，交付来源更新为 **`cbc61703347c407413f8a732a6ca9a5637258eba`**。相对前述代码审查提交，最后一项源码变更是 `OpportunityEvidence.tsx` 的公开样例短句文案；前述用量与模板独立代码结论不扩展为本人对 P12/Coverage 的自审批准。本段只核对构建输入、实际产物和交付日志。

判定：**Mac arm64 本地候选的文件完整性、来源绑定和已提供的构建/隔离冒烟证据 PASS。分发签名、公证、Windows 实机和真实后台能力不在此 PASS 内。**

独立生成的 [mac-package.json](mac-package.json) 记录 145 个生产构建输入的 SHA-256；逐个比对当前文件与该提交的 Git blob，全部一致，生产输入目录没有额外未跟踪文件。输入包含生产源码、本地图标、打包器、自有构建代码、依赖锁和配置。排序输入清单摘要为 `57119b39059de43a31378c339f8b2fee1fc5b3f710a57556518fef53de4b433f`。这是构建后对 Git 输入、产物和重建输出的独立绑定，不声称产物内有签名的 Git provenance 或 ZIP 可重复构建。

| 实际产物 | 字节数 | SHA-256 |
| --- | ---: | --- |
| `desktop/out/意客AI-darwin-arm64/意客AI.app/Contents/Resources/app.asar` | 1,754,693 | `1d59f506a3b5e588da6f9f5dd052911532260aaf7c51eb67940f9604160c6131` |
| `desktop/out/make/zip/darwin/arm64/意客AI-darwin-arm64-0.2.0.zip` | 122,467,836 | `9333ef6398c568f699bfe7265de3d524612e01f4679b65d1e95f75b62595cffe` |

本人独立检查结果：

- 重新执行 `verify-package.mjs`，退出 0，结果与 [package-check.json](package-check.json) 完整一致。ASAR 内主进程、preload、renderer manifest 及资源共 39 个文件与实际 `.vite` 输出一致；其中 37 个 renderer 文件也与生产排除检查重新构建的输出逐字节一致。
- ZIP CRC 通过；其中 258 个常规文件、14 个符号链接与实际 `.app` 对应内容一致，未遗漏 `.app` 常规文件。打包图标与批准的源 `yike.icns` 摘要相同。
- ZIP 文件名使用 UTF-8 字节但没有设置 UTF-8 标志；Python 默认 CP437 解码会显示乱码，因此审计按原始字节重建名称。独立使用 macOS `ditto -xk` 在临时目录解压，中文 `.app` 名称保留、ASAR 摘要相同，退出 0。此 Mac 验证不能推导其他系统解压器的文件名兼容性。
- ASAR 的 35 个文本代码/配置资源及所有路径未发现隔离视觉 harness 的入口/标识；[production-exclusion.log](production-exclusion.log) 同时记录 4,751 个生产模块、0 个 manifest harness 引用、实际 ASAR 已检查、无失败。这里的排除检查不是通用秘密内容扫描。
- `codesign -dv` 实际显示 `Signature=adhoc`、无 TeamIdentifier、无 sealed resources；`stapler validate` 返回 65 并确认没有附加公证票据。**不能作为已完成 Developer ID 签名和公证的客户分发包。**

已只读核查的主线程证据：

| 证据 | 实际结果与限制 |
| --- | --- |
| [mac-build.log](mac-build.log) | `npm run make:mac`，darwin/arm64、应用版本 0.2.0，完成 ZIP 与 postMake；主线程报告该构建退出 0。存在 Vite 弃用警告，不是构建失败。 |
| [final-tests.log](final-tests.log) | 76 文件通过，829 项通过、21 项跳过；此完整套件早于 `cbc6170` 最后的单文件文案修正，跳过不能计入通过。 |
| [sample-copy-regression.log](sample-copy-regression.log) | 最后修正后 3 文件、56 项通过。命令提供了 4 个筛选项，但 `outreach-completion.test.tsx` 不存在，实际只匹配 3 文件；按实际结果记账，不报 4 文件通过，也不称再次运行全套。 |
| [typecheck.log](typecheck.log) | `tsc --noEmit` 无诊断；这是主线程提供的执行日志，未由本段再次运行。 |
| [packaged-smoke.log](packaged-smoke.log) | 有明确 PASS；运行实际 ASAR 的 main/preload/renderer、固定 IPC、未配置服务、临时 CSV/JSON 写入、取消及确认退出。保存/退出对话框在隔离进程内替换，不能当作用户原生对话框或可见 `.app` 启动/重启验收。主线程报告退出 0。 |

所有上述日志的字节数和摘要已写入 `mac-package.json`。本人未重开正式客户端、未操作真实客户数据、未修改产品源码或提交。最终截图配对与响应式由主线程另行验收；Windows x64 构建、安装、退出重启、卸载与系统缩放，以及真实计量、平台执行、模型和发送服务仍需各自证据。

## 远端合入后的最终整合复核（追加）

本段绑定 **`14aa73ea32a417a067b558b61f692a56fa8ba06b`**，正常合并父提交为 `830509bd32ae8216f890f4a1646c12c587773c8c` 与 `639b17dd01d592188cd8ce83f069c626b957d43f`。旧 CBC 的 `mac-package.json` 和其中记录的七份日志保持原样，摘要复核无变化；共同的 `desktop/out` 产物路径现已由整合包替换，旧摘要仅代表历史构建。

**合入源码的独立增量审查 PASS。** 生产桌面仅 [servicePolicy](../../../desktop/src/main/servicePolicy.ts)、[client](../../../desktop/src/renderer/services/client.ts)、[shared contracts](../../../desktop/src/shared/contracts.ts) 三处变化：新增两个固定短信登录 operation，主进程对手机号、验证码、试用码长度和额外字段做严格校验；没有让 renderer 指定来源、路径、管理员身份或任意请求。调用继续经过原可信 sender、固定 HTTPS Origin、串行 cookie、重定向拒绝和 JSON 边界。client 校验冷却时间与认证结果，保留 501/未配置错误，不把登录成功当成 R4 执行能力已可用。

R4 用量、空间代次、TaskWizard、未决操作账本及草稿源码未被此次合入改动。生产 session 目前仍未提供 R4 所需的可信 `accountScope`，真实研究用量/执行 adapter 也未接通；对应启动保持原合同的阻断，不生成虚假空间或默认消耗。此次不扩大为手机登录后端或短信实际送达的完整审查。

本人独立执行 `tests/servicePolicy.test.ts`、`tests/ui/phoneClient.test.ts`、`tests/serviceClient.test.ts`：**3 文件、23 项通过**，工具输出 `bde839`。仅用隔离 transport fixture，没有发送真实短信。主线程本提交的 [完整套件](integrated-tests.log) 为 **77 文件、845 项通过、21 项跳过（共 866）**；与局部套件重叠，不相加。[typecheck](integrated-typecheck.log)、[make:mac](integrated-mac-build.log)、[ASAR 冒烟](integrated-packaged-smoke.log)、[TEST 排除](integrated-production-exclusion.log) 的日志已审阅，主线程报告串行构建链均退出 0。TEST 排除仍为 4,751 个生产模块、0 个 manifest harness 引用、实际 ASAR 已检查、无失败。

独立产物记录见 [integrated-mac-package.json](integrated-mac-package.json)：

| 内容 | 结果 |
| --- | --- |
| 构建输入 | 145 项均匹配该提交 Git blob；仅上述三处源码相对 CBC 变化；排序输入摘要 `25b3e37dd646cc07c2c80153fb203b4c41fca125eefd9c25f9e97fe97f2ad98a` |
| ASAR | 1,755,773 字节；SHA-256 `4586f2f12dc6c571cdf763a0dd19462bb922f80719aed28b3a8e204f3840dec6` |
| ZIP | 122,467,968 字节；SHA-256 `ed56fac5404e7e5d9c98bf3421a812879cc073b0545ff0c2668afd180a7f4b60` |
| 文件绑定 | 独立 `verify-package` 退出 0并与 [记录](integrated-package-check.json) 完整一致；39 个打包文件匹配 `.vite`，37 个 renderer 文件匹配重新构建输出 |
| ZIP 与品牌 | CRC、258 个常规文件、14 个符号链接和批准图标全部匹配；macOS `ditto` 临时解压中文名称和 ASAR 摘要正确 |
| 分发边界 | 仍是 ad-hoc 签名、无 TeamIdentifier/sealed resources；无附加公证票据，stapler 退出 65。ZIP 未设置 UTF-8 标志的兼容边界同前，仅原生 Mac 解压得到验证 |

整合包的文件完整性、来源绑定和所给隔离冒烟证据通过；这不是新包的完整可见原生 UAT。主线程尝试打开独立新进程时，CUA 无法可靠区分同 bundle ID 的旧 R3 窗口，实际选中了旧窗口，随后仅停止本次新进程。**该旧窗口明确排除，新包可见启动/退出/重启验收记为未完成。** 受控 ASAR 冒烟也不能替代这一项。

本轮仅新增整合摘要并追加本报告，未修改源码或提交。Windows 实机、Developer ID 签名/公证、真实 SMS、R4 计量和平台能力仍须分别验收；前文对本人自作 P12/Coverage 的独立性排除继续有效。
