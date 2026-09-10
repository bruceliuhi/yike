# 搜索建议明确未受理恢复

Base335274e9ef9291be4119a238bb689f9a30381fe2。接续[客户端已记录缺口](2026-09-11-search-suggestion-client.md#实施与验证)，不重做建议链。只测变更路径，整批一次独立审核、修复仅差量、最终renderer只构建一次。无真实模型调用。

## Task 1：服务端可恢复的未受理事实

- [ ] 工作树 `/tmp/yike-v02-scope.Pwf9Fs`，仅改 `pilot/search_suggestions.py`、`pilot/search_suggestion_service.py`、新增 `migrations/129_v02_search_suggestion_rejections.sql`、更新 `deploy/grant_search_suggestions.sql` 和相关Python定向测试。root负责db注册、TS/UI和文档。不要改对方文件、不spawn。先RED再实现，只追加所属文件commit，不amend共享HEAD，不push。
- [ ] 新增不可变owner/tenant隔离的拒绝记录：原请求ID、完整请求+disclosure的指纹、有限原绑定信息、固定reason、created_at；不存description/密钥、不外发、不扣模型额度。不改110/128迁移字节。FORCE RLS，应用只有SELECT/INSERT；更新原grant严格角色/可达ACL检查覆盖新表。不必给未知profileVersionId加外键，拒绝不声明画像合法。
- [ ] `store.reject(claims, request, disclosure, reason)` 只接受规范且accepted=true的profile-description-v1授权快照（hash/provider/model限长格式验证）。reason白名单：capability_unavailable、disclosure_mismatch、profile_unavailable、suggestion_busy、suggestion_rate_limited、suggestion_quota_exceeded。复用reserve同一tenant事务锁11001及原会话认证。锁内先找实际请求和已有拒绝：同指纹返回原事实，不同409；不存在才插入拒绝。真实受理先赢则返回实际PENDING/终态，不得声称未受理。
- [ ] reserve在同锁内检查拒绝tombstone，若原请求已拒绝返回原拒绝回执+None，不调度、不新扣额度。replay_receipt/get_receipt同样可读拒绝，进程/服务重启或模型关闭后仍可查。缺回执仍404，不凭缺失生成未受理；会话/数据库错误保持未知，不能反向升级成拒绝。
- [ ] 新回执保持既有四绑定字段、profile_sha256/model_provider/model_name/disclosure_policy_version、rule_version、created_at/updated_at；`state='NOT_SUBMITTED'`、`result=null`、`usage=null`、`error_code=上述reason`、`profile_current=false`（未核定可采用资格，不作画像状态判断）。模型信息是原确认快照，不宣称实际调用过。回执不能触发finish或执行。
- [ ] service仅在确定尚未reserve的配置/快照/画像/忙碌检查，以及reserve事务明确quota/rate/profile/disclosure失败时调用reject。已有请求冲突、鉴权、DB不可用/提交未知、实际调度后异常一律不走reject；reject失败保留原错误/未知。先replay，再新请求准入；无condition锁跨DB。有效但模型配置变化的原请求仍可读；false/畸形disclosure仍普通422/409，不伪造有效授权。
- [ ] 补少量真实受限PG测试：拒绝可GET恢复且不扣quota、拒绝后reserve不会调用模型、先受理再reject返回真实回执、改body409/跨用户不见；证明锁序拒绝/受理不能双事实。API沿既有POST/GET返回无需新路由，使用真实受限PG+合成模型边界，不真实provider。复用独占cached postgres:16-alpine，精确清理自己的容器及卷；只补fixture129/grant，不重跑整个旧模型/process套件。
- [ ] 简短报告到绝对私有git-dir/sdd/search-suggestion-rejection-backend-report.md，记SHA/实际测试/失败/未验；测试Python `/tmp/yike-main-merge.PZkSlU/.venv/bin/python`。不写产品sdd。声明完成前告知root，不并发stage/amend。

## Task 2：客户端明确结束（root）

- [ ] shared schema只在NOT_SUBMITTED接受固定拒绝reason，原请求完整绑定仍必须匹配；PENDING/UNKNOWN/404/普通异常不解锁。
- [ ] 原绑定的未受理回执可持久、重开只GET；显示原因和“明确未受理，不曾调用模型”，用户明确结束后才重新读取业务介绍并再次批准，不自动生成新UUID/POST。NOT_SUBMITTED无采用按钮，不混为FAILED生成结果。
- [ ] root注册129、定向adapter/UI恢复测试、整批独立审核及一次renderer构包后推main；现有45 UI和后台证据只在受影响处复用，不无差别重跑。

## 实施与验证

源码 `6e8b16a9aa49c32349cb15f4cdd1914e64ce790f`（root客户端与迁移注册 `d30cecd`），非作者整批审核GO，无阻断项；范围为完整 `335274e..6e8b16a`。129不可变拒绝事实与原受理表互斥，原请求重复读取不调度；普通POST/GET复用，不增加自由模型入口。只有reject/reserve及互斥写入guard取租户锁，replay/get是只读查询。

- Python建议store/service定向45通过；专用受限PG/HTTP新增5通过、64未选择。使用合成画像/模型，专用容器及卷已删除，不操作共享/客户库。
- TS传输严格状态及UI重开恢复/明确结束/再次确认2项先RED后通过，20项未重复执行；tsc通过。实际合成PG/HTTP回执JSON另由客户端真实schema解析通过。
- 未重复模型/process及其他后台全套检查。真实供应商调用、业务数据外发、平台操作、Windows包/实机、生产和客户UAT均未执行。
- 独立补查10项错误边界：会话/DB/冲突不生成拒绝、拒绝落库失败不声明未受理。最终源码单次renderer生产构建通过，不是Windows安装包或生产发布。

恢复语义：NOT_SUBMITTED只表示服务端持久证明这个原请求未被受理，不等同于供应商扣费账单。未知、超时、会话/数据库异常和404都不自动解锁。用户可明确结束匹配的未受理记录，再核对最新业务介绍/模型并重新批准；系统不会自动换ID重试。
