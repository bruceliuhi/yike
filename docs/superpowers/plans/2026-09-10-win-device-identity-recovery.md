# 本机设备身份恢复 Implementation Plan

> **For agentic workers:** REQUIRED: subagent-driven-development、TDD及独立SPEC/代码/架构/质量审核。按仓库约定，本次并行片使用一个短期`codex/win-device-identity-recovery`分支，验证审核后合回main；root唯一Git写入者。本文细化既有设备HTTP计划Chunk2，不新增产品布局或授权机制。

**Goal:** 将已审HTTP、OS保护vault和服务端挑战签名组合为可重启恢复、可换会话证明的本机身份流程，最终接上真实采集入口。

**Architecture:** 固定服务origin/服务端已认证user作用域下持久保存原登记及当前证明请求；主进程协调器只用固定HTTP六操作，未知先GET，不盲目重登或跨会话重放completion。后续main负责真实会话代次与窄IPC，renderer不提供身份或签名字节。

**Tech Stack:** TypeScript/Zod、Node fs/Ed25519、现有Electron safeStorage保护接口、Vitest、FastAPI/PostgreSQL。

基线`bc04860`。依据[设备HTTP计划Chunk2](2026-09-10-win-device-http-client.md)、[登记恢复合同](../../contracts/V02_DEVICE_REGISTRATION_RECOVERY.md)、[设备持钥合同](../../contracts/V02_DEVICE_KEYS.md)。Mac后端不修改；该架构与任务书已批准的本机恢复范围一致。

## Chunk 1: 原请求、密钥找回与身份协调

状态：Task1～3全部实现、根463项及独立SPEC/代码/架构/质量PASS，见[限定QA](../../qa/V02_DEVICE_IDENTITY_RECOVERY_WIN_REVIEW.md)。以下为原验收清单；Chunk2普通入口仍未完成，实际HTTP/PG和原生双进程已先行验证组合，不代签入口。

### Task1 持久请求记录

Files: 新建`desktop/src/main/deviceIdentityJournal.ts`、`desktop/tests/deviceIdentityJournal.test.ts`。

接口：`createDeviceIdentityJournal({directory,protection})`使用现有`DeviceKeyProtection`。scope精确`{serviceOrigin,userId}`；record精确`{version:1,scope,registration:{request_id,device_label},proof:null|{deviceId,sessionId,request:DeviceChallengeRequest}}`。sessionId为本机随机UUID代次，不是令牌、Cookie或服务端session_digest；正文/签名/私钥不入账本。

- [ ] 可导入stub先RED。`loadOrCreate(scope,label)`返回`{record,created}`；`read(scope)`只读或null；`setProof(scope,registrationId,expectedProofId,proof)`按原登记及旧proof request_id（可null）做CAS，返回新record。参数全部在await前校验/快照。
- [ ] 固定绝对目录+scope摘要文件；同scope只产生一个原登记UUID/规范标签，之后传入新标签不改原记录。复用OS保护，没有明文回退。严格scope/record校验、64KiB有界读取、损坏/不匹配/符号链接停止，不删旧文件或造成功。
- [ ] 同文件跨factory串行。初次独占创建；更新使用同目录独占临时文件→write/sync/close→rename→目标文件sync，读取已有完整文件仍sync。任一存储/保护失败固定错误；失败文件保留，不把异常后内容可读当成功落盘。CAS冲突不写。
- [ ] Tests: 重建factory和16并发保持同登记；scope隔离/输入突变、规范Unicode标签、密文无原标签、proof CAS、损坏/过大/保护失败、write/sync/rename失败不返回成功及完整写入后重新读取恢复。定向Vitest/tsc及独立两阶段审核。

### Task2 已绑定设备只读找回密钥

Files: 修改`desktop/src/main/deviceKeyVault.ts`、`desktop/tests/deviceKeyVault.test.ts`。

- [ ] RED：新增`read(scope):Promise<DeviceKeyMaterial|null>`，复用scope校验、OS保护检查、锁与已存在密文读取/sync，不mkdir或生成密钥。缺失返回null，已有损坏/保护不可用仍固定错误。
- [ ] 保留getOrCreate原行为；read跨factory/输入突变安全。Tests验证缺失不写、已有键相同、失败不覆写、与getOrCreate并发读取一致。定向vault/signing回归及独立审核。

### Task3 主进程身份协调

Files: 新建`desktop/src/main/deviceIdentitySession.ts`、`desktop/tests/deviceIdentitySession.test.ts`。

接口：`createDeviceIdentitySession({serviceOrigin,deviceLabel,transport,journal,vault,nowSeconds?})`；transport仅`requestDevice`。deviceLabel为可信main固定标签（正常装配使用“意客AI Windows客户端”），构造时按登记schema验证并快照，不接renderer身份/标签，已有登记永远保留原标签。`prepare(session,{retryRegistration?,retryProof?}={})`中的session由可信main提供`{userId,sessionId,isCurrent():boolean}`，不来自renderer。返回仅`{state:'READY',deviceId,credentialVersion}`或`{state:'REGISTRATION_UNKNOWN'|'PROOF_UNKNOWN'|'REVOKED'|'KEY_MISSING'|'KEY_MISMATCH'|'SESSION_CHANGED'|'FAILED',error?:固定code}`，不泄露签名字节/密钥/路径。正常main装配另属Chunk2，不能把本注入边界冒称已装配。

- [ ] stub先RED。每factory串行prepare，在入队前快照session/选项；每个await后及下一个HTTP/存储/签名前检查isCurrent，旧代次迟到不产生READY或后续写请求。
- [ ] 新登记原UUID/标签落盘后才POST；已有记录先原GET。404不是未提交证明，默认返回REGISTRATION_UNKNOWN；只有显式retryRegistration才用原UUID/标签POST。超时/服务未知返回UNKNOWN，下一次仍先GET，不自动POST。
- [ ] 原回执严格绑定后GET当前identity；REVOKED停止。0/null时getOrCreate并等落盘，已绑定只read：没有本地密钥KEY_MISSING，公钥不同KEY_MISMATCH，不自动替换/轮换。
- [ ] 新证明先persist request，再challenge→signDeviceChallenge原字节→complete→parseDeviceProofReceipt。版本0用BIND，否则PROVE；成功后再GET identity核对当前版本/公钥，才READY。每个阶段失败不伪造成功或自动重试。
- [ ] 已有proof先GET原receipt：同sessionId成功且当前identity仍匹配才可READY；同sessionId PENDING/404/结果未知默认PROOF_UNKNOWN，显式retryProof才用原request取挑战/完成。REJECTED/EXPIRED在下一次明确prepare可生成新UUID，不能重放消耗挑战。
- [ ] 旧sessionId只读历史，绝不完成旧challenge。读到确定响应（包括404/PENDING）后，当前prepare可按最新identity持久新代次请求并做BIND/PROVE；不把旧SUCCEEDED提升为本会话证明。旧请求读故障仍UNKNOWN；版本竞态按服务拒绝返回，不盲循环换UUID。
- [ ] Tests: 完整首次BIND/新会话PROVE、原登记/完成回执丢失GET恢复且无多余POST、同代次显式重试原UUID、重建协调器、历史成功非当前授权、旧PENDING不跨会话complete、撤销/丢键/错键、各种固定失败、CAS/存储失败不请求、队列并发、退出/换账户在各await节点迟到均无后续动作。
- [ ] 运行新三套+deviceRegistration/deviceProof/deviceProofSigner/deviceServiceClient/serviceClient/servicePolicy/preload/windowPolicy，tsc；独立SPEC及整片质量审核。

## Chunk 2: 正常产品装配与真实验收（不得用模块测试代签）

- [ ] `main.ts`由真实session.get取得userId，本机代次在登录/退出请求进入时立即失效；窄prepare/status IPC，userData固定路径+safeStorage正常装配。已有UI按真实状态展示并接后续执行入口；新视觉/流程变化遵守现设计授权。
- [ ] `tests/test_desktop_device_identity_http_postgres.py` + `desktop/tests/integration/device-identity-live.test.ts`通过实际Node→HTTP→受限PG首次登记/BIND、重启新会话PROVE、丢回执恢复、防重复和退出/撤销拒绝；可先验证Chunk1组合，但不得因此标记本Chunk或产品入口完成。
- [ ] Windows独立safeStorage生命周期/生产TEST排除、确认发送/候选相关回归及非作者终审；后接05F执行原文签名和来源worker，真实来源/收发/安装/UAT继续单独验收。

## 交接

Win独占上述desktop新模块、vault最小扩展及自有验收；Mac设备/执行/回复/授权P2收口仍由Mac处理。按SHA/实际结果同步任务书；不擅自外发、付费或部署，也不把一片完成当全Goal完成。

## Chunk 2 执行细化：既有设备页正常入口

沿已批准的主进程持钥/现有设备页设计，不新增平台能力或使用授权含义。设备身份与商业授权/平台连接分开；既有管理服务仍管理其原授权，不能把 BIND 冒充购买或平台登录。实现核对后保留原 bind/解绑管理入口，在同一设备区域添加“本机身份”行并复用现 Modal 组件，避免原管理 BOUND 驱动本机证明或取消已有管理操作；独立 identity 弹窗不改变页面布局框架。

- [ ] Task4：新增 `desktop/src/shared/deviceIdentity.ts`（严格 `{retryRegistration?,retryProof?}`，受限结果/状态 schema、固定两频道）；新增 `desktop/src/main/deviceIdentityController.ts` 及测试。factory `{service, identityFactory}` 让原 coordinator 使用拦截401的专用 transport；`requestApi(unknown)`代理原固定API，login/loginPhone/logout进入即生成新UUID并清空本机结果，所有401只失效自己的代次。auth操作在途时prepare不排到旧身份上，返回BUSY。`prepare(unknown)`先严格解析快照选项，再通过真实session.get严格取得 authenticated:true/user_id；用户名1～256码点/无控制字符/边界空白，永远不接受renderer身份或路径。新的同user登录也必须新证明；每异步完成检查代次，串行忙碌防重，异常固定FAILED。`getStatus()`只读本机最近观察，初始NOT_PREPARED，非实时授权；退出立即清空。coordinator READY严格解析，只传deviceId/credentialVersion，其他状态只传固定code，无签名/密钥。
- [ ] Task5：root修改main.ts固定userData子目录（device-keys / device-identity）与safeStorage，构造真实journal/vault/coordinator/controller；三个handler均trustedSender，普通API改走controller，不改变runtime NOT_READY，不暴露requestDevice。preload只增加getDeviceIdentityStatus/prepareDeviceIdentity固定频道，类型合同新增可选方法兼容旧包，现preload始终提供；定向测试含冻结入口/原签名不可达/main实际装配与恶意来源拒绝。
- [ ] Task6：root复用Settings设备区域及原bind弹窗，新增专用DeviceIdentityPanel与UI测试。真实桌面两方法存在且非样例时显示本机身份操作；浏览器/旧包/样例保留原管理流程。无需输入用户ID或密钥。首次明确确认→prepare；结果未知先核对，另一次明确确认才retry原请求。状态文字区分上次身份核验通过、未核验、未知、缺失/撤销/会话变化；始终注明不是平台已连接/使用授权。切账号、退出、关闭卸载忽略迟到结果；仅本次busy禁止重复按钮。保留既有授权/导出等功能，不重排页面。
- [ ] Task7：TDD有效RED→GREEN，控制器、preload、实际main装配、Settings/管理与既有身份定向+tsc；非作者SPEC后质量审核。一次生产候选构包在本批真实入口完成后做，沿已通过原生/PG字节证据不重复整套；实际运行观察普通入口与未知/失效提示，不将TEST或只有绑定当整链完成。Git由root串行、验证后main同步；高级管理不扩展。

验证命令从desktop运行Node24 `node_modules/vitest/vitest.mjs run tests/deviceIdentityController.test.ts tests/preload.test.ts tests/deviceIdentityMain.test.ts tests/ui/device-identity-panel.test.tsx tests/ui/settings.test.tsx` 与 `node_modules/typescript/bin/tsc --noEmit`。新边界测试必须先失败，已有同字节模块证据不重复全量；字段/集成真实错误按风险追加。
