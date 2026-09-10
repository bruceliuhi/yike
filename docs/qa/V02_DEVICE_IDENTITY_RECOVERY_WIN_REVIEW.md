# Windows 设备身份恢复：限定工程接收

2026-09-10，基线 `bc04860`。入口为 main 专用 `createDeviceIdentitySession.prepare`，尚未接普通 main/UI；不得记为平台连接、真实采集或客户验收完成。

## 已验证动作

- 原登记先加密落盘再 POST；丢回执后重建对象，按原 UUID GET 找回，不重复登记。
- 首次 BIND、原完成回执恢复、新登录会话 PROVE；已绑定设备只读找密钥，缺失/错键/撤销停止，不生成替代身份。
- 每个异步边界检查会话代次；旧成功不是新会话授权，未知结果默认只查原请求。
- Windows Electron 43.4.1 两个独立进程使用实际 safeStorage，恢复相同登记、密文和密钥，并完成产品签名器验证。隔离临时目录，非产品 userData，未模拟断电。

## 证据与审核

本片完成前执行的结果，后续同字节直接引用，不重复构包/全量测试：

- journal 有效 stub RED 52 fail/1 pass → 53 pass；coordinator 46 项有效 stub RED → 46 pass，再补既有行为覆盖至 61 pass。vault read 首轮 5 fail/34 pass，补非目录反例后最终 40 pass；不把测试夹具错误当产品 RED。
- 根代理 Node24：journal/session/vault/registration/proof/signer/deviceServiceClient/serviceClient/servicePolicy/preload/windowPolicy **11 文件 463 passed、0 skipped，793ms**；`tsc --noEmit` exit 0。
- 实际 Node→socket HTTP→受限 PostgreSQL：`tests/test_desktop_device_identity_http_postgres.py` **1 passed、0 skipped，2.50s**。此前协调器 stub 实际请求测试 RED 为 FAILED 与 REGISTRATION_UNKNOWN 不符。真实登记和证明落库，丢弃已提交的响应，数据库核对仅一次登记、BIND/PROVE 两个成功请求及不同服务端会话；撤销/跨用户/退出拒绝。仅隔离合成账号，无实际平台或客户数据；专用 PG 容器已精确移除。
- Windows 原生报告：`C:\Users\bruce\AppData\Local\Temp\yike-native-device-vault-ACUx43\result.json`，两进程所有检查 true。登记 ID、密钥摘要和密文摘要两次一致。报告保留本机，不将它当安装包或 HTTP 证据。
- 非作者 SPEC 对 vault、journal、coordinator 及 HTTP/native 夹具 PASS；最终 coordinator 独立 61 pass。非作者代码/架构/质量最终 PASS，无可操作问题；没有重复运行根代理的 HTTP/原生测试或把根代理结果冒充独立运行。

源码 SHA256：journal `848149fb546f0dbba792564c3b705da90a861f754171f5fd7e2e2d680f88b87c`；coordinator `299b6cb70fd485e0f1e1001ac71ff6bd3b719a5a7fc3e076ab077a40de1d194c`；vault `7d153a9f189b2323eb8f0dfc489090114de9b781be67ae6a922faa1423c10abc`。提交前再次读取摘要与原生报告吻合。

## 下一入口与交接

Win 继续真实 session.get 派生身份、登录/退出即时失效、窄 IPC、userData/safeStorage 与现有账号页面装配，再接执行签名和来源 worker。Mac 保留设备/执行/回复后端，避免重复开发。原文证据、多找类似、短句建联和真实发现→判断→确认联系→跟进仍为首发目标。

Mac `69a0cb2` 来件中会话撤销 GRANT 已恢复 SELECT/INSERT，源码层关闭此前多授 UPDATE/DELETE 的 P2；此处只做差异核对，不代签新的部署/RLS 测试。普通产品入口、实际平台、确认收发、安装发行及 UAT 未完成，05D/F 与 Goal 继续。

## 普通设备入口（基线3c4da16，2026-09-10）

入口：账号与授权→设备与使用授权→核验本机身份。复用原页面/Modal，原商业绑定/解绑保留；明确确认后主进程从真实session.get派生身份，使用固定userData与safeStorage。退出/重新登录进入即失效；未知先核对原请求，重试再次确认。上次身份核验通过不代表平台、使用授权或runtime就绪。

验证：root页面/服务/preload/main及旧管理回归7文件35项/tsc通过；作者controller最初51有效RED、异步补强2RED、严格合同6RED，最终93项/tsc通过。根增强controller→真实HTTP→受限PG **1 passed/0 skip，2.62s**，原登记/BIND/PROVE、防重与退出迟到均核对，专用容器已移除；本次增强测试首次通过，不伪造RED。独立SPEC与整批代码/架构/质量最终PASS；两项严格合同修正独立6项通过，先前UI/main独立20项不重复运行。源码最终shared C347C59E/controller9E8F3A92（完整摘要在Git对应文件可算）。后续只构建本批一次候选，实际平台/收发/客户UAT仍未完成。

候选已生成：固定源码 **e5774b6**，本机 `desktop/out/candidate-e5774b6/YikeAI-Setup.exe`，同目录简短验收说明。一次make-win成功，385输入构包前后逐字节一致（manifest `99460de707b2bfa2ffe46ea55f39957311f25aa55b25eaa398e9c0198f36166f`）；结构与原生包内启动冒烟通过。安装包SHA256 `1b3c688a5a448068713b44d70f252bc1d3198b981edea463c5a7ae2dea392ef2`，ASAR `143b6819aa74e0a642ef8d8d50d66be8afe1a25a085e1b16be74f8e07b7c0def`，NotSigned。直接扫描本ASAR无TEST入口、含两窄身份方法；首轮扫描命令未处理Windows前导反斜杠而失败，修正检查命令后通过，产品未改/未重新构包。人工安装及本包真实账号操作仍未验收；无服务配置时不会伪报可用。

期间保留Mac23a68b6为252d482，客户端来件与身份适配定向40项、回复API纯HTTP2项通过；未改本包、未将它追认为最新main。Mac回复更正两项P2仍以交接为准，新增API不自动关闭；不重复构包或全量测试。
