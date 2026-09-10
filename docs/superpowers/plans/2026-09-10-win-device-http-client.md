# 05D/05F 设备 HTTP 与身份恢复客户端 Implementation Plan

> **For agentic workers:** REQUIRED: Use `subagent-driven-development`; TDD、独立SPEC及代码/架构/质量审核。用户已授权直接main与持续执行；root唯一Git写入者。沿已批准设备设计与现有R3/R4入口，不重做Mac后端，不新增通用签名IPC。

**Goal:** 客户端可靠登记本机、持有已落盘的私钥并完成当前会话BIND/PROVE，恢复原请求而不重复登记，作为实际采集执行的前置。

**Architecture:** 复用`deviceProof`、`deviceKeyVault`与`deviceProofSigner`。主进程专用设备HTTP操作与现有登录/退出共用ServiceClient队列；renderer仍只有原公开白名单。再接主进程持久状态与已有连接/执行入口，不把HTTP底座完成写成设备已连接。

**Tech Stack:** TypeScript/Zod、Node Ed25519/fs、Electron safeStorage、Vitest、FastAPI/受限PostgreSQL。

基线`86e5f48`；延续[已有设备签名计划Chunk2](2026-09-10-win-device-signing-client.md)、[登记恢复合同](../../contracts/V02_DEVICE_REGISTRATION_RECOVERY.md)、[持钥合同](../../contracts/V02_DEVICE_KEYS.md)。用户已批准现有产品流程；本片不改变界面布局、私钥保护方式或平台授权，不需要新视觉设计。

## Chunk 1: 固定主进程设备传输

开始实现前已快进到`4f36cc2`，新增仅Mac验收文档。Chunk1独立计划审核Approved；原签名/vault/公开传输5文件95项通过（451ms），是基线而非新增功能证据。

### Task1 严格登记与当前身份协议

Files: 新建`desktop/src/shared/deviceRegistration.ts`、`desktop/tests/deviceRegistration.test.ts`。

- [x] 可导入stub先RED，覆盖精确登记输入`{request_id,device_label}`、原登记五字段、当前身份四字段；UUID规范小写，标签按Python strip/Unicode码点及合法Unicode处理，输入4KiB；不接owner/tenant/path/key/时间。
- [x] 导出`deviceRegistrationRequestSchema`、`deviceUuidSchema`、`parseDeviceRegistrationReceipt(raw, expectedRequest)`与`parseDeviceIdentity(raw, expectedDeviceId)`。回执原request及规范标签匹配，不把SUCCEEDED当ACTIVE。identity零版本只允许null公钥，正版本只允许canonical Ed25519公钥，REVOKED照实读取。
- [x] 错误只固定`INVALID_DEVICE_REGISTRATION_RECEIPT`/`INVALID_DEVICE_IDENTITY`，不回显原输入。完整反例与合法回执通过后独立SPEC/质量审核。

### Task2 复用会话队列的私有六操作

Files: 新建`desktop/src/main/deviceServicePolicy.ts`、`desktop/tests/deviceServiceClient.test.ts`；修改`desktop/src/main/serviceClient.ts`，不修改公开`ApiOperation`、preload或renderer白名单。

私有调用统一精确`{operation,payload}`：register的payload为登记正文；registration/receipt为`{request_id}`；identity为`{device_id}`；challenge为`{device_id,request}`（request使用已审挑战schema）；complete为`{device_id,challenge_id,proof}`（proof使用已审完成schema）。路径字段不混入POST正文。全部在入队前解析、复制及序列化；登记字节上限按未规范化输入检查，避免超长空白被trim掩盖。

- [x] RED：`createServiceClient`提供主进程专用`requestDevice(input)`，公开`request(input)`拒绝全部六设备动作。新私有入口只接固定operation/payload，不接URL/header/tenant。
- [x] `validatedDeviceOperation`严格映射`devices.register`→POST device-registrations、`devices.registration`→GET原request、`devices.identity`→GET当前身份、`devices.challenge`→POST已知device key-challenges、`devices.complete`→POST已知device/challenge complete、`devices.receipt`→GET原key-request。复用已审challenge/completion schema，仅BIND/PROVE，不开放ROTATE。
- [x] 新入口复用原execute/queue/pending限制、Origin/no-store/有界响应/超时/退出清cookie；队列验证在入队前冻结完整payload，登录→设备请求→退出严格有序。没有自动重试，读取不产生POST；原public请求行为不变。
- [x] `node node_modules/vitest/vitest.mjs run tests/deviceRegistration.test.ts tests/deviceProof.test.ts tests/deviceServiceClient.test.ts tests/serviceClient.test.ts tests/servicePolicy.test.ts`通过，`tsc --noEmit`通过；独立审核后提交限定传输片。

Chunk1代码`eb43216`：独立SPEC、代码/架构/质量均PASS，根代理342项及类型检查通过；原候选真实HTTP/PG三项回归通过，详见[本片QA](../../qa/V02_DEVICE_HTTP_CLIENT_WIN_REVIEW.md)。下列Chunk2没有据此完成。

## Chunk 2: 本机持久恢复与产品装配（后续，不用Chunk1代签）

- [ ] 接续文件`desktop/src/main/deviceIdentitySession.ts`及专项tests：固定服务origin/已认证user，登记原UUID与标签先fsync；原登记GET后再读identity并比对本地vault公钥。404不证明在途POST未提交，显式重试用同UUID/标签；不按名称领设备。新建密钥必须落盘后才BIND，已有公钥不同/撤销/保护不可用停止，不自动覆盖/轮换。
- [ ] 主进程流程原BIND/PROVE request在挑战前持久化，复用signer签服务端原字节；未知先GET窄回执，不重放跨会话旧completion。当前会话变化后任何晚到结果不变成可执行身份；先处理退出/取消再接新的用户。
- [ ] 在`desktop/src/main/main.ts`正常装配vault、持久记录和会话协调，仅向已有UI暴露窄“本机准备/查询状态”入口，不导出公私钥、挑战正文、签名或任意文件路径。按现有连接流程显示未知/失败/撤销，未安装平台仍不假报已连接。
- [ ] 新`tests/test_desktop_device_identity_http_postgres.py`与`desktop/tests/integration/device-identity-live.test.ts`实际Node→HTTP→受限PG登记/BIND/PROVE/原请求恢复/撤销和退出拒绝；Windows独立safeStorage运行证据和原有发送/候选相关回归、生产TEST排除、凭据扫描、非作者终审。随后接05F固定执行签名字节和来源worker，真实平台/收发/发行/UAT继续单独验收。

## 交接

Win独占以上desktop和自有验收测试；Mac现登记/设备/执行API、116迁移、回复后端所有权不变。每片提交同步唯一任务书和Win/Mac交接，状态按实际覆盖记录。本片不执行外部平台采集、发送、付费或生产部署；后续真实采集按现行产品范围和可用平台权限验收，外发、付费与生产部署另需明确授权。
