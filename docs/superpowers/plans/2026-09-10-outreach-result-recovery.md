# 07B 持久结果恢复

基线b968f9b；沿用已批准07B收发与原请求恢复，不新增UI/渠道/权限。上一批已有本机一次消费和私有签名链，本批补结果落盘→重启按原resultId补交。按既有TDD与独立整批审核执行，只跑受影响测试；不构包、不实际发送。

结果槽只保存SENT/FAILED明确回执。native UNKNOWN没有新的投递事实，CLAIM已记录UNKNOWN，session直接保留未知、不占用不可变最终结果槽、不额外提交空RESULT，避免妨碍后续平台查证。

## Task 1：不可变加密结果记录

独立Agent仅新增desktop/src/main/outreachResultOutbox.ts及desktop/tests/outreachResultOutbox.test.ts。导出OutreachResultRecord（requestId、claimId、deviceId、contextSha256、resultId、outcome:NativeOutreachOutcome）及OutreachResultOutbox接口read(scope,requestId):Promise<record|null>、put(scope,record):Promise<record>、工厂createOutreachResultOutbox({directory,protection})。scope复用OutreachConsumptionScope的origin/user/tenant，不绑定session或credentialVersion。严格123结果语义和opaque/sha/time；返回固定新对象，输入在await前快照。只保存结果元数据，不保存正文、Cookie、私钥或签名。

文件名按scope/requestId哈希；同一个scope/requestId只有一份不可变记录，相同内容可重放，任何resultId/claim/device/context/outcome改变拒绝，不覆盖。用可信固定目录、OS保护加密、排他创建和fsync，POSIX同步目录；缺损、解密失败、符号链接、异常不当作不存在，不泄露底层错误。可参照已有消费日志，不重构旧日志。测试只覆盖落盘重建/隔离/冲突/损坏/并发/无明文/存储失败关键路径，不复制庞大测试矩阵。不commit或push。

## Task 2：接入现有会话

根修改outreachDispatchSession及其HTTP测试：配置outbox必需，CLAIM前检查原记录；已有记录只走签名RESULT，不再CLAIM/driver。valid native结果先以原身份落盘，再申请RESULT签名；即使期间注销也保存真实晚回执。保存失败返回明确非持久pending，不伪装可重启恢复；任何路径都不撤销原消费记录。新增resumeResult(原绑定,signal)，只读原记录并按当前合法会话/同设备凭据提交原resultId/原outcome，无记录不猜测结果、不重新发送。reconcile继续只GET。记录不可变保留，服务端回执成功不删除，重放靠原resultId幂等。

## Task 3：同结果跨凭据版本恢复

根核对123重放：凭据版本属于当前传输认证，不改变原结果事实。若原resultId已存在，允许同owner/device/claim/context/resultId/outcome在当前有效credentialVersion下返回原回执；其他任何变化仍冲突。原数据库payload/digest不改写，新增传输不篡改历史。以一个真实PG/HTTP定向用例证明，不重跑全库测试。

本批之后仍须真实driver/main/Win UI和部署验收；本地加密/fsync不宣称Windows实机或所有断电情况已验证。独立审核集中一次，失败仅差量修复。

## 本批验证

后端新增真实设备密钥轮换用例先RED 2失败（原结果409冲突），修正重放语义后本批2项+既有原请求/失败回执2项在实际HTTP/受限PG共4 PASS/7 deselected；原始payload和digest未改写。一次性数据库已清理，不影响客户库。

根session从缺outbox模块RED开始，真实localhost HTTP+实际加密文件重建链11 PASS；服务/平台返回仍是明确合成fixture。outbox专项9 PASS见[模块短报告](2026-09-10-outreach-result-outbox-report.md)，不重复运行。根统一tsc发现测试fixture将literal true推断为boolean，仅修精确测试类型后tsc退出0；中间只补返回类型仍失败一次，见短报告。未改变生产约束，无全量回归、构包或真实发送。整批独立审核待记录。
