# 05F前置设备持钥与签名客户端 Implementation Plan

> **For agentic workers:** REQUIRED: Use `subagent-driven-development`; TDD and independent spec/code/architecture/quality review. 用户授权直接main，根代理唯一Git写入者，按独立文件分工。不改Mac共享设备/执行API、runtime或111/115。

**Goal:** 在Windows主进程安全持有设备私钥，实际消费服务端BIND/PROVE挑战与窄回执，供05F真实签名执行接续；不让用户手填令牌或把证明当采集授权。

**Architecture:** 严格公开设备协议→主进程标准Ed25519签名/OS保护存储→同产品会话串行的固定HTTP流程→已有账号/执行入口消费。签名只针对经过绑定校验的服务端原始payload；不开放任意sign/文件路径/密钥导出IPC。旧策略/启动账本原样保留。

**Tech Stack:** TypeScript/Zod/Node crypto/fs、Electron safeStorage、Vitest、实际FastAPI/受限PostgreSQL测试。

基线`22bae22`，继承已批准R3/R4与[设备合同](../../contracts/V02_DEVICE_KEYS.md)、[执行合同](../../contracts/V02_EXECUTION_RUNTIME.md)和原05C接续。原文证据/多找类似/短句建联仍为首发必需；这是执行身份前置，不是扩大高级加密/轮换工作。

进度更新（正常合入主线`a9d18db`后）：**Chunk1独立模块完成并通过非作者SPEC/代码/架构/质量审核**，根97项/类型检查与实际Windows两进程OS保护→产品挑战签名组合通过，见[实际验收](../../qa/V02_DEVICE_SIGNING_CLIENT_WIN_REVIEW.md)。Chunk2产品会话/HTTP尚未接；Mac执行载荷入口仍待实际接收。利用接口接续窗口，Win下一片优先[现P11/R4固定原文证据](2026-09-10-win-fixed-source-evidence.md)，不继续扩高级密码或管理功能。

## 当前事实与不越过的边界

- 现有desktop仅通用HTTP桥接，没有设备私钥或持钥流程。服务端BIND/PROVE、设备登记及窄回执均已共享注册。ROTATE增强不在本片；已有服务端能力不删除。
- 05F执行签名原文必须含服务端认证tenant/user/session_digest。当前公开session不提供完整上下文，execution API尚无签名payload入口。Win不猜tenant、不读取/暴露Cookie、不将device PROVE原文/回执当execution签名。最小执行载荷接口由Mac串行补齐，另行合同接收后接05F START/CANCEL；不复制其runtime或改签名域/111。
- 使用Node标准Ed25519与Electron OS保护，不自造加密算法。Windows不能用明文或内存密钥假装已安全落盘；safeStorage不可用时禁止绑定，已有文件不覆盖、不删除。平台Cookie/会话隔离与设备私钥是不同数据，不能互用。
- 服务origin、已认证user和设备ID共同绑定本地记录，路径由受信userData子目录与其SHA256派生，不接收renderer路径；密钥正文、签名和payload不进日志/renderer/localStorage。退出登录清空当前操作上下文，不删除已有加密密钥。
- 每个BIND/PROVE记录原UUID/期望版本/公钥及结果；创建BIND挑战之前先保存私钥。网络未知先查询原request，不换钥或重建BIND；证明成功回执不能代替当前活跃状态。重新登录后新PROVE使用新UUID，旧未决completion不跨会话重发。

## Chunk 1: 严格设备合同与保护签名器

### Task 1: 公开合同与原字节绑定

**Files:** Create `desktop/src/shared/deviceProof.ts`, `desktop/tests/deviceProof.test.ts`。

- [x] 写RED：BIND/PROVE输入严格UUID/版本/nullable公钥；canonical base64url32/64字节；服务端challenge四字段与signing_payload所有12字段精确匹配：protocol、tenant_id、user_id、device_id、request_id、challenge_id、session_digest、operation、expected_credential_version、target_public_key、nonce、expires_at。拒未知字段、错用户/设备/原request/operation/version/target_public_key、内外challenge_id/expiry不同、原字节非ASCII或重复JSONkey、过期/过大payload。返回原始字符串不重新序列化。仅接受`yike-device-proof-v1`，不接受execution域；合法Unicode身份允许以Python的ASCII转义形式出现。
- [x] 导出`deviceChallengeRequestSchema`（BIND/PROVE）、`deviceCompletionSchema`、`deviceProofReceiptSchema`、`parseDeviceChallenge(raw, expected, nowSeconds)`及上下文绑定的`parseDeviceProofReceipt(raw, expected)`。challenge expected固定为`{serviceOrigin,userId,deviceId,publicKey,request}`，其中userId来自服务端session.get，request为严格challenge request；receipt expected仅`{deviceId,request}`。tenant/session摘要只允许来自受信HTTPS挑战，校验有界非空ID/64位小写SHA，不返renderer。服务origin与vault一致，仅规范HTTPS或现有开发loopback HTTP；Python身份字符串长度按Unicode codepoint，不按UTF-16单元，UUID不凭空收窄服务端允许的版本位。
- [x] 为避免JSON重复键签名歧义：payload必须ASCII，完整比较Python `json.dumps(sort_keys=True,separators=(',', ':'),ensure_ascii=True)`等价表示与原文；固定ASCII字段名排序，字符串沿用JSON转义并将DEL与非ASCII UTF-16单元转为小写四位转义，包含BMP与非BMP代理对。使用实际Python生成的跨语言golden覆盖中文/emoji/DEL与控制字符；不是仅比较普通JSON.stringify。签名始终保留服务端原字节。payload.challenge_id/expires_at必须分别等于外层字段；nonce必须canonical base64url32字节。nowSeconds必须有限安全整数，`nowSeconds < expires_at <= nowSeconds + 150`，明确允许服务端时钟最多快30秒，服务端最终120秒有效期判断不变；不延长已过期挑战、不无限放宽。
- [x] 窄回执严格五字段；SUCCEEDED必须预期credential_version（BIND1/PROVE原版本），其它状态必须null，request/device/operation必须匹配。只把SUCCEEDED记录为历史成功，不生成执行token。
- [x] 运行`node node_modules/vitest/vitest.mjs run tests/deviceProof.test.ts` RED→GREEN、`node node_modules/typescript/bin/tsc --noEmit`；独立规格及代码/架构/质量审查。

### Task 2: 标准密钥与不可明文回退存储

**Files:** Create `desktop/src/main/deviceKeyVault.ts`, `desktop/src/main/deviceProofSigner.ts`, `desktop/tests/deviceKeyVault.test.ts`, `desktop/tests/deviceProofSigner.test.ts`；Windows显式验证夹具为`desktop/tests/native/deviceKeyVault.cjs`及`verifyDeviceKeyVault.mjs`，不接产品构建入口或自动Vitest。

- [x] RED：无OS保护时不生成/保存；文件读取失败/损坏/身份不符不替换；不同service/user/device不同记录；并发首次创建只有同一持久键；文件中无明文私钥；renderer无法提供路径。真实Node生成/验证Ed25519签名，不只mock签名成功。
- [x] `createDeviceKeyVault({directory, protection})`仅主进程使用；protection封装isEncryptionAvailable/encryptString/decryptString，目录来自app.getPath('userData')固定子目录。`getOrCreate(scope)` scope={serviceOrigin,userId,deviceId}全部校验，derive SHA256文件名。用crypto.generateKeyPairSync('ed25519')，privateKey以标准PKCS8 PEM放入加密记录，publicKey以JWK.x的canonical base64url32字节表示；读取时重新派生公钥校验。记录严格含version=1/scope/publicKey/privateKey，返回只供主进程的`DeviceKeyMaterial {scope,publicKey,privateKey}`；错误只固定code。
- [x] 首次文件以独占创建、同步写入并fsync后可供BIND。写入失败保留现场并报错、不先POST；并发EEXIST读取同一原文件，不覆盖。使用同进程per-scope串行避免读取半写入；跨进程由已有Electron single-instance限制，损坏文件failclosed保留。不得自动删除/修复未知文件。实测新增反例：完整写入但sync失败后，下一次读取仍须在同文件句柄成功sync才返回，不把能读到完整密文当作已持久成功；持续sync失败持续拒绝，不改变密文或密钥。
- [x] signer导出`signDeviceChallenge({key, challenge, expected, nowSeconds})`，key为上述持久键，challenge为原始服务端响应，expected同Task1。临签再次调用parseDeviceChallenge，校验当前期望用户/设备与key.scope及本机公钥一致，不允许把早先parse结果当无限期签名许可；服务origin由主进程受信HTTP实例绑定，不接受renderer输入。签原UTF-8字节并用本机公钥实际验签，返回completion窄签名给受信HTTP流程，不导出通用sign IPC。
- [x] 执行两个定向test与tsc。真实Electron safeStorage验证用独立受控临时profile，不覆盖产品userData；至少实测isEncryptionAvailable、encrypt/decrypt与重建vault保持公钥。没有真实Electron结果明确未验收，不能用注入保护fixture冒充Windows验收。
- [x] 非作者两阶段审核并根代理提交，记录源码与实际检查范围。

## Chunk 2: 主进程真实BIND/PROVE消费（接续检查点）

共享HTTP/队列接线需在Chunk1通过后收敛精确接口再补独立可执行计划，不提前实现一个未审通用签名桥。目标是固定devices登记/只读、challenge/complete/receipt内部操作，同一serviceSession与logout串行；原request记录和本机密钥先持久化、未知不换键。实际Node客户端→共享build_app→受限PG完成BIND/PROVE/查询/撤销后拒绝，沿用现有`tests/test_device_credentials_postgres.py`夹具或新的Win自有桥接测试文件，不改Macstore。登记POST目前无幂等request_id，未知登记不能盲重发或从租户全部设备列表按标签冒认，需要明确恢复策略后接UI。

## 后续05F与整链

Mac补执行signing_payload固定入口后，Win严格核对完整operation与原request/策略/设备/连接版本再签原字节；START/CANCEL原UUID恢复独立于05C；CLAIM/RENEW/真实worker与候选上传接同一路径。搜贝、research硬上限、monitor调度和类似/补查来源不能只因签名成功就开启。按已支持真实模式贯通并展示未支持范围，不缩减产品最终目标。
