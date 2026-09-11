# 业务资料用于联系草稿

> 执行：subagent-driven-development；根代理客户端、后端代理独立文件实现，整批一次非作者审核。基线 `0fb934d`。

**Goal:** 把已批准的资料引用范围接入真实草稿保存及发送前核对，客户能选择本人已确认、允许外用的原文片段，并保留出处和历史。

**Architecture:** 复用现有资料列表、草稿JSON和确认/执行路径，不建资料副本或新营销发送通道。原资料内容与草稿引用由服务端校验，撤销影响包含当前草稿；操作历史不变。方案依据 `UI_MATERIALS_CONTRACT.md` 与完整产品计划触达中心要求，不新增页面或商业范围。

**Tech Stack:** Python/Pydantic/PostgreSQL，Electron/TypeScript/React/Zod。

## 约束和本批边界

- 使用现有隔离工作树，其他checkout不改；不要重跑全量测试/构包。
- 本批先贯通人工选取真实资料片段→草稿→确认发送前资格检查；模型自动选材/有出处改写继续完整任务，未完成前不宣传已实现。现有不了解引用的短句教练不能悄悄丢弃此出处或处理已撤销来源。
- 只有本人同租户最新 READY、external、未移除且精确版本/提取ID匹配的资料可新增引用；不得自动将internal升级为external。quote须逐字存在资料正文和当前草稿，旧画像可引用本人其他画像下的合格资料，但不返回其他作者正文。
- 声明引用不是证明全部人工文字真实；用户自行输入/复制内容不能被追溯伪造为正式出处。历史已发不能撤回，撤销后尚未开始发送须阻止；正在外部执行无法承诺撤回。
- 新确认包含引用身份，不能仅按草稿文字比较；原请求恢复与未知发送不重试继续保留。

## Task 1: 服务端真实引用、影响和发送核对

负责 `pilot/contact_drafts.py`、新 `pilot/contact_material_references.py`、必要 `pilot/material_references.py` / `pilot/materials.py` / 现有触达执行校验、相关最小授权脚本和 `tests/test_material_contact_references.py`。不修改desktop。

接口：草稿增加可选 `materialReferences`，最多3项，按用户选取顺序；每项严格只有：

```json
{"sourceProfileVersionId":"UUID","materialId":"原资料ID","materialVersion":4,"extractionId":"原提取ID","quote":"逐字原文"}
```

materialId/extractionId为非空≤200字符串；materialVersion为1..2147483647整数；quote为非空非空白≤2000、无NUL文字；去重精确条目。缺字段兼容旧Draft/旧JSON，显式空数组合法，不以null代替。

```python
# 原有九项数组必须原样保留；仅存在新字段时追加以下一项。
if hasattr(snapshot.draft, 'materialReferences'):
    fields.append([ref.model_dump() for ref in snapshot.draft.materialReferences])
```

- [ ] 定向RED：有效external引用保存且回执/最新读取保留原文出处，hash变化；internal/旧版/撤销/他人/跨租户/quote不匹配均不能新增保存；无字段老草稿保持原hash/payload。复用现有受限PG和机会fixture，不调用平台/外部模型。
- [ ] 最小实现：保存前从真实身份解析author、资料最新记录并校验；引用资格并入现有发送context及最后发送前检查，不能只有前端保护。对同一资料owner使用与资料变更兼容的锁顺序，短事务，不跨网络持锁。原请求读取保留历史成功回执，不伪装资料当前仍有效。
- [ ] 已定位CLAIM后仍有渠道核验等待：新增现有签名协议动作 `VALIDATE`（与CLAIM同字段，resultId/outcome为null），只核对现有UNKNOWN的精确claim/context/device/session/key和原deadline，不重新CLAIM、不延长许可、不修改结果。返回严格 `{state:'QUALIFIED',requestId,claimId,contextSha256,dispatchBefore}`。服务端在短事务内重新运行引用/草稿/连接资格。客户端有非空引用的执行，在渠道check后、journal.consume及execute前调用此动作并精确比对；失败保留UNKNOWN、不外发。此处是最终资格确认的时点，之后已进入执行的网络动作无法原子撤回；不能承诺撤回已发许可。统一锁顺序 material owner→draft owner→device/connection→profile，queue入口也先取material；历史RESULT和UNKNOWN查询不因来源撤销被阻止。
- [ ] 在现有material impact和token引用摘要中加入实际最新草稿的引用身份/请求ID/quote摘要；新草稿引用使旧token失效。撤销/改版/移除后新保存/确认/尚未执行触达失败，但不删除旧草稿。避免额外索引表；如实际并发路径要求额外结构先报告，不自扩。
- [ ] 定向PG：新引用使旧impact token失效；撤销可看到draft影响；撤销后发送准备/最终执行核对拒绝而历史可恢复。跟随现有发送状态机，不重发未知结果。
- [ ] 运行新增及必要旧摘要/确认测试，记录命令和RED/GREEN；独立提交后短报告。不make、不部署。

## Task 2: 普通编辑器采用、保存和原生边界

负责desktop共享draft/schema/hash，ContactEditor及单独小型资料引用控件、NativeSendConfirmation/main核对，定向UI/schema测试。

- [ ] RED：允许外用且READY的资料证据可单独选择带入；internal不显示可用项、来源加载失败可重试；每次只明确采用一段，不自动保存/生成/发送。采用后保存接口保留refs，重新读取不丢失；修改/解除引用使草稿待保存、确认失效。
- [ ] 基于现有details/Field/Button增加“引用业务资料”，列出当前画像本人资料的证据片段；服务缺失时不造假入口。已有不同sourceProfile引用保留可读身份，不自动扫其他资料正文。身份/画像/渠道切换及迟到回执不得串入另一草稿。
- [ ] 新 `draftMaterialReferenceSchema` 与Python同字段同边界；可选refs加入ContactDraft及所有原生strict schemas。摘要算法仅有字段时追加数组，renderer/main/Python相同；保存恢复/脏状态/发送fingerprint核对包含refs。
- [ ] 根代理同步 `outreachDispatchProtocol.ts` 的VALIDATE签名字段，`outreachDispatchSession.ts`提供最终资格校验回调，`outreachConsumer.ts`有非空引用时强制调用、回调缺失失败。保留无引用旧执行、持久consume防重及迟到RESULT记录，不用来源撤销伪造未发送。
- [ ] 草稿显示引用片段及版本；明确“移除引用片段”同时移除所选逐字片段和该引用，不偷偷把失效引用洗成人工事实。编辑导致片段不再匹配时提示，必须重新选用或明确移除引用后才能保存。其余人工文字保留。
- [ ] 有资料引用时，当前短句教练提示暂不支持有出处改写，不发模型请求；后续同一完整Goal接入引用感知模型，不把原帖quote当资料证据。不得静默清除refs以启用旧coach。
- [ ] 只跑新增UI/共享hash/原生引用边界与必要TypeScript，不全量、不构包。

## 收口

- [ ] 单一独立整批代码/架构/质量复核，修复仅差量重验。正常push main，记录精确SHA及未验边界；本批不追认Windows候选或真实发送完成。
- [ ] 更新资料契约及任务书/整合入口，引用本文件唯一实施证据。完整V0.2、真实跨行业模型/平台/客户/部署验收仍继续。

## 实施与验证

执行中。
