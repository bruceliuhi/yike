# 三平台原任务恢复：实际 HTTP/PostgreSQL 联验

基线 `dc075af780dc623472a32f2d1cbf64f94261c7f5`。不新增产品范围，验证上一批跨层实际接线；来源内容仍为合成数据，绝不作为平台/Windows/商业证据。

## Task 1: 一个有真实协议约束的贯通场景

复用 `tests/test_desktop_foreground_collection_http_postgres.py` 中的真实策略/账号登记/签名原生controller、loopback HTTP、受限PostgreSQL fixture，新增一个单独三平台场景（可以新建专用 Python/TS integration 文件，避免重写旧单平台用例）。测试仅运行新增案例。

- 真正保存/确认三平台策略及三条本人连接，使用显式 `three-platform-foreground-v1` 能力；平台顺序 XHS→抖音→B站，核对真实execution.task和START都保留确认顺序。
- 真实Node identity/session/signing/journals/controller→socket HTTP→真实后端策略/执行/候选存储→受限PG，不替换resolver、执行服务、签名或候选上传。只有来源driver返回已标注合成内容；每次driver接收绑定的平台账号、独立profile和固定预算都检查。
- 总预算设置可证明均分与余数分配，driver返回不超过分配额的原文记录；每个平台仅启动一次、原文不变。
- 第二个平台真实candidate POST落库后丢失响应，第三个平台不能启动。停止/重建controller后，RECOVER只查原批次并完成原FINISH，不重采；再显式resumeStart，读真实task与前缀RUNNING/false回执后仅启动第三个平台。
- 最后真数据库验证同一任务SUCCEEDED、3个平台都SUCCEEDED、原START只有一条、没有重复候选批次/观察、前缀CLAIM/FINISH无重复。本次返回源记录预算合计不超过原总额。
- 不伪造成功输出，不吞测试失败，必须无skip。环境变量若缺失可按现有fixtures跳过，但本次验收必须实际运行。不能把测试admin连接传给Node客户端；私有session/签名key不得出现在输出、日志或Git。
- 只写测试文件；如发现产品缺陷，向根报告根因与最小修复，不自行扩大修改。根负责隔离PG、文档与最终提交。共享现有 `yike-identity-contract-pg` 不可碰。
- 一次独立审核测试有效性，不重复产品构包或已有全量测试；无真实平台/模型/消息/生产调用。

## 状态

最终源码候选 `55a3b540a28526b7d0906789109cb4dadd6e7c75`，产品修复 `cb44a60605cab273ee2526f5aec5e812d5df2f6b`。实际联验、定向测试及独立修复差量审核 **GO / 本批代码与协议链**；完整V0.2未完成。

核对更正：上一批审核R3把 `_locks` 内部排序误当HTTP输出。`pilot/execution_runtime.py:get_task` 第536行自 `990ebca8` 即按target_order重新排序；taskFeed亦保留确认顺序。这不是产品缺陷，本批不修改该正确排序、不篡改响应制造乱序；已有客户端按ID映射及乱序合成测试仅属防御性处理，不作为真实接口乱序证据。R1任务级FINISH与R2缺日志不能证明未执行的修复仍有效。

实际联验发现的产品断点：第二个平台开始的openWorkerScope与每50ms的STATUS进度查询争用identity的preparing短互斥，后者可能让来源切换得到BUSY并将任务置为本机FAILED（服务器仍RUNNING）。不能以撤掉轮询绕开。根代理补最小controller内部scope获取队列，仅串行身份获取，不锁采集或修改全局identity授权；来源切换的身份/取消/代次围栏保持。确定性反例先失败（同一时刻2次进入），修复后controller全文件29 passed。真实HTTP用例保留轮询，最终1 passed，无skip；该修复同批独立审核后才能合入。

## 实施与验证

- `tests/test_desktop_multiplatform_foreground_http_postgres.py`：首轮修复后**1 passed in 6.93s**。实际Node session/Ed25519签名、连接REGISTER/VERIFY、socket HTTP与受限PostgreSQL；身份prepare、OS vault、账号probe/login及来源driver是测试fixture，三个隔离profile不构成真实OS密钥库或平台登录证据。Node显式断言不持有数据库环境变量。
- 同一任务顺序XHS→抖音→B站，预算10分配4/3/3，返回1/2/1条合成原文。抖音POST落库后丢响应，B站不启动；重建controller后仅读取两个原批次并补FINISH，不重采/不重复POST；显式恢复原START后仅启动B站。
- 数据库核对任务与三个平台SUCCEEDED，START=1、CLAIM=3、FINISH=3、批次=3、观察=4。task与START真实响应均保持确认顺序，没有人为改序。
- `vitest run tests/foregroundCollectionController.test.ts`：**29 passed**；`tsc --noEmit`：退出0。未重复其他全量测试、renderer构建或Windows构包。
- 使用独立临时PostgreSQL容器 `yike-multi-chain-0911`，未碰共享数据库；来源/账号/凭据皆为合成测试数据。此证据不等于真实平台采集、实际模型质量、Windows、生产或客户UAT。

首轮独立审核发现一项P2验收缺口：只查状态/计数，尚未证明原文落库不变；不是FIFO产品缺陷。`55a3b54`仅补Python场景，按tenant/owner联接四条观察、来源与版本，先核对行数再逐条比较正文（真实组合音标、emoji、空白、换行、tab）、标题、来源链接及各项摄取元数据。仅重跑此场景，最终 **1 passed in 7.08s / 无skip**。TypeScript和产品字节不变，复用原29项/tsc证据；RoleDatabase通过`SET ROLE`执行受限SQL，不等于生产连接ACL验证。

非作者 `multiplatform_http_final_review` 仅复核补断言差量，最终 **GO**，该P2关闭，无新增P1/P2；未追加全量测试或重复构包。下一步真实平台、Windows新payload/正式候选及生产/客户UAT；不得把本次协议链联验写成平台上线。
