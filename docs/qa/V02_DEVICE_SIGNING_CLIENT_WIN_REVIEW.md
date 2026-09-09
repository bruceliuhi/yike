# Windows设备持钥客户端分片验证

2026-09-10，计划基线`22bae22`，正常保留Mac固定原文证据`4cb9524`及普通服务装配认领`4101379`形成`a9d18db`。本页只记录05F前置的标准持钥/合同模块，不声称已接产品HTTP、实际平台、安装或发送。完整Goal继续；原文证据、多找类似、短句建联均保留首发要求。

## 分工与主线

- Win认领与最小execution-signing-payload提案`e5c6bd1`已经由正常主干同步，不替Mac写接收ACK。Mac保留execution_api/runtime与115，Win只新增桌面独立模块。
- Mac入站15文件经Win独立只读审查无P1/P2；根代理新增`tests/test_opportunity_evidence.py`实跑14 passed/0.05s，合入后pilot/tests/deploy/migrations与Mac精确一致。此次不是PG/客户端消费ACK。首次push遇Mac并发4101379拒绝，正常fetch/merge后推送a9d18db并核实远端相同，未强推。

## Vault：实际红绿与持久化

根代理先写可导入stub和29项断言：29项因`DEVICE_KEY_NOT_IMPLEMENTED`失败，随后29项通过及tsc通过。新增部分写入/完整写入但sync失败反例时30通过、1失败：第二次读取没有flush便返回，错误把完整密文当作持久成功。

修复仅为既有文件用不截断O_RDWR句柄读取、成功sync后返回；不改密文、不换键、不自动删除文件。31项通过，再补持续sync失败反例后最终**32 passed / 523ms**。涵盖标准Ed25519/PKCS8/JWK公私钥一致、密文存储、身份/服务/设备绑定、双vault实例16并发同键、调用期间scope修改、固定安全错误、部分写入/损坏不覆盖及成功flush恢复原键。

单测注入进程内AES-GCM保护夹具，只验证依赖边界，不能当OS保护证据。

## 真实Windows原生保护检查

在desktop目录用Node24.19执行`node tests/native/verifyDeviceKeyVault.mjs`，通过现有rolldown单独构建真实vault模块，启动两次真实Electron43.4.1进程；不创建窗口，不接网络，不使用产品userData。子进程只继承系统路径/临时目录白名单，使用windowsHide，30秒超时，报告仅公开摘要与布尔结果。

首次白名单版本的受控profile位于`C:/Users/bruce/AppData/Local/Temp/yike-native-device-vault-Ic1PPM`，结果`result.json`与合成加密密钥保留，不进入Git。两个独立进程均验证safeStorage可用、实际加解密、重新创建vault与真实Node签名；重启前后公钥摘要及密文摘要相同：

- vault源码SHA256：`fa5198e6b7c063d8bd3ba4b132ada32d5af55fff54a3a76327d616cf604773f5`
- 公钥SHA256：`680e0093cc846379a33b83f9458a8f2a1d633377f5618b16128504cf7922c781`
- 密文SHA256：`01efb378808b7d3575f7cc0d2870ed137492c0dfc0006f388003a0b15bf08a3c`

失败保留：第一版验证脚本调用TypeScript旧编译API，实际锁定TS7入口只导出版本，`ModuleKind.CommonJS`缺失导致未启动Electron；改用仓库现有rolldown后验证通过。早先完整环境继承的原生探针也通过，但采用系统环境白名单版本作为证据，不把失败回填为通过。

最终整合探针继续实际构建新`deviceProofSigner`与`deviceProof`，由vault读取的同一密钥经产品挑战校验/签名函数处理受控服务端格式挑战（包括中文身份），再实际验签；不是仅在夹具里直接调用crypto.sign。最终路径`C:/Users/bruce/AppData/Local/Temp/yike-native-device-vault-6x892G/result.json`，两独立进程全部布尔检查true，源码摘要与冻结模块一致：

- signer源码SHA256：`48a0fbc0c838fcf3c8f2f357703c7d6298419d838016f496e8145eae9aea9483`
- challenge源码SHA256：`cea9e449e84d439892a97b0c75771fc758d95f1bcb51710cc79320a7369cebf4`
- 最终两进程相同公钥SHA256：`1675b30430874ad2849a5e95df12bfa8b5835d60a0f1a2a7cc23d01ed570fdb3`
- 最终两进程相同密文SHA256：`727bec70320e0993f1a55d0801db78ac66388498ae1f6e2fb37bca3196dad166`

## 合同、签名与相关回归

共享合同作者先跑stub：34项中33失败/1通过；实现34通过。回执原请求绑定新增1失败→35通过；UUID版本位/256 Unicode codepoint/公共HTTP三项反例失败后修正；非ROTATE previous_signature反例失败后只接受null/缺省。最终37项通过、tsc通过。实际Python生成中文/emoji/DEL/C0的ensure_ascii golden已固化测试；签名使用原字符串，严格12字段/内外绑定、canonical base64url、重复JSON键及8KiB上限，不重写原文。

独立文件作者负责signer：真实Node密钥15项stub失败→15项通过，临签重验scope/有效期/公钥与PKCS8私钥派生关系，签原UTF8并实际验签，异常仅固定错误，不导出任意sign IPC。

根代理运行`vitest run tests/deviceProof.test.ts tests/deviceProofSigner.test.ts tests/deviceKeyVault.test.ts tests/serviceClient.test.ts tests/servicePolicy.test.ts tests/windowPolicy.test.ts`：6文件96 passed/533ms。最后补一个UUID尾换行拒绝回归（现代码直接通过，无新增故障或生产修正），vault33项，最终同命令**6文件97 passed / 717ms / 0 skipped**；`tsc --noEmit` exit0。上述集合重叠不相加。未重复全仓、renderer构包或安装，因为本片未改产品入口/renderer；实际原生专属构建与两进程验证见上，不拿旧安装包覆盖新模块。末次只读进程检查未发现本片原生夹具残留Electron。

## 独立审核

非作者`store_lock_audit`分两阶段对冻结8文件完成SPEC与代码/架构/质量审核：**PASS，无剩余P1/P2**。独立运行共享合同+signer共52项及tsc通过；另用实际Python生成6组Unicode BIND/PROVE载荷，经当前产品signer/Node验签通过，6次过期重验均拒绝。原生结果仅只读核对，不冒充其自行重跑；根代理97项与独立52项重叠不相加。

审核确认生产模块未接任何任意签名IPC、未读取Cookie/服务端密钥；回执只描述历史，未提升执行能力。完整写入后sync失败的恢复路径及最终真实native组合均已复核。源码摘要与上述冻结值绑定；新增vault测试文件最终SHA256为`e0f7ca9af8f2c822b233405349491b6972f0a472a647a3956c32917572d221f5`。

## 尚待接续

设备链还需同一登录会话串行设备登记、BIND/PROVE、原UUID恢复和现有账号页接入；登记POST当前无幂等键，未知不得盲重试或按租户设备标签冒认。执行签名载荷入口等待Mac实际合同接收，不能提取Cookie/另一签名域代替。CAPTURED原文nested DTO已到主线，Win下一片优先按[计划](../superpowers/plans/2026-09-10-win-fixed-source-evidence.md)接现P11/R4；不等待执行接口时继续扩高级安全，也不把固定历史原文当当前可访问或联系批准。
