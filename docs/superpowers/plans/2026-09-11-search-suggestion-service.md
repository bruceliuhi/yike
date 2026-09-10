# 搜索建议服务接续

基线 `ff20acd72809b04ec65905a6d9b0c09c458db7df`。执行已批准的[04B/05C方案](2026-09-09-win-search-suggestions.md)，不重新设计产品。复用110请求/配额、现有模型和有总截止的子进程；先接认证服务和普通runtime，再接现有条件编辑器。只跑受影响检查，整批一次独立审核，修复只看差量。没有客户授权，不运行外部模型。

## Task 1：授权、后台服务与认证接口

- [ ] 在当前隔离工作树 `/tmp/yike-v02-scope.Pwf9Fs` 实现；只改 `pilot/search_suggestions.py`，新增 `pilot/search_suggestion_service.py`、`pilot/search_suggestion_api.py`、`migrations/128_v02_search_suggestion_consent.sql` 及对应定向测试。不得改runtime/web/ui_api/db或客户端，root负责这些共享文件。先测试后实现。
- [ ] `SearchSuggestionService(store, model=None)`，接口 `available`、`preview(claims, profile_version_id)`、`submit(claims, payload)`、`get_receipt(claims, request_id)`、`close(timeout_seconds=5)->bool`。复用store认证和ProcessSearchSuggestionModel，不另造模型。未配置/关闭拒绝新生成；原回执始终可查（即便模型不可用），不能因退出丢查询能力。
- [ ] 预览只读本人已确认画像，返回当前 `profile_version_id/profile_sha256/description/model_provider/model_name/disclosure_policy_version`，policy固定 `profile-description-v1`。模型目的地由服务器配置，预览不调用模型。用户须看到完整业务介绍并显式批准，不把画像已确认当外发授权。
- [ ] 严格提交包含现有四项SearchSuggestionRequest字段，额外 `disclosure` 对象：`accepted:true`、`profile_sha256`、`model_provider`、`model_name`、`policy_version`。它们是用户确认的预览快照，不是客户端选择任意模型。新请求须匹配当前受控模型和锁内已确认画像摘要，才reserve和调用。旧请求绑定同一正文/授权；重复同请求返回原回执，不调用，不因后来配置变化阻止读取。同ID改授权或正文409。旧无授权请求不能被重放升级为有授权。
- [ ] 128在110请求表加可空 `disclosure_policy_version`，旧行保持NULL；授权和原请求/画像摘要/模型/时间同次事务持久化，更新不得改授权。不要修改110迁移字节；128需可重复应用兼容现有migrate重放110再128。既有store.reserve允许可信内部不带授权（旧测试兼容且不能触发service外发），新增可选disclosure核对、授权纳入原请求摘要，公开回执含policy。无新表或权限扩张。
- [ ] 最多2个模型工作者、4个已接收工作（含排队）；满载原请求仍可读，新请求拒绝且不reserve。获取槽后reserve，重放立即放槽。先commit PENDING，后台单次执行，POST快速返回原回执。完成复用finish原会话/画像复核。未知不重试；明确未调用的submit失败/排队取消写dispatch_failed；已开始异常保守UNKNOWN。后台落库失败保留原PENDING可查，不泄露正文或异常。
- [ ] close先拒绝准入，取消未开始工作，调用model.close的有界清理并共用总预算；未确认退出返回false，不能宣称释放/停止。后台线程与槽释放准确，进程重启遗留PENDING不再调度。竞争测试涵盖提交/关闭、满载重放、同ID并发、完成会话或画像变化，优先复用旧store/process证明。
- [ ] `register_search_suggestion_api(router, service, identity, require_session_https)` 注册 GET `/search-suggestions/preview?profileVersionId=...`、POST `/search-suggestions`、GET `/search-suggestions/{request_id}`，固定安全错误、严格JSON重复键/额外字段/大小限制；认证和同步DB工作移到threadpool，HTTP/Origin/no-store复用父router。无服务返回501；不接caller tenant/user/description/URL。
- [ ] 写服务定向测试及至少一个真实受限PG+HTTP授权→原请求恢复测试，使用合成模型边界，不访问外部模型。独立PG用缓存postgres:16-alpine精确命名/随机端口，不操作已有共享PG。测试需要新128时显式应用；root注册default migration。精确清理自己的合成容器和卷。
- [ ] 只提交所属文件；简短报告到绝对私有git-dir/sdd/search-suggestion-service-report.md，说明SHA/命令/失败及未验边界。不要写产品目录sdd；不push。

## Task 2：普通runtime装配（root）

- [ ] 注册128；新增独立 `YIKE_PILOT_SEARCH_SUGGESTION_BASE_URL/API_KEY/MODEL` 配置，不隐式沿用评分模型凭据。全缺保持不可生成，部分配置安全失败，不输出秘密。
- [ ] runtime装配store+service+ProcessSearchSuggestionModel；build_app/ui_api串行接线及有界shutdown；capability据实际服务而不是硬编码打开。回执查询不依赖模型是否配置。
- [ ] 定向配置/路由/退出测试；只复用已有模型/process测试证据，不重跑其187项。服务交付后单次独立整批审核和必要修复，审核通过后同步main。
- [ ] 用户客户端生成/预览采用/持久原请求恢复仍为下一接续；不把服务API当客户端已可用、不标04B/05C或Goal完成。纯后端批次不重复构建未变化的桌面包。

## 实施与验证

本批源码 `29c3710a0ee15609df19b04e498ae3c4c7905df3`（root装配 `f9cae8b`），非作者最终审核GO，无P1/P2。审核范围为完整 `ff20acd..29c3710`，独立补查满载重放、第五请求不预留、关闭预算与关闭后查询通过；未重复全量测试。已实现Task1与Task2服务端接线；客户端仍未接入，不升级父卡或完整Goal状态。

- 接口：认证 `GET /api/ui/search-suggestions/preview?profileVersionId=...`、`POST /api/ui/search-suggestions`、`GET /api/ui/search-suggestions/{request_id}`。请求及授权快照持久化，画像/模型绑定，旧请求只读恢复；返回建议不执行采集。服务器配置见[部署说明](../../../deploy/README.md)。
- 定向 unit/API/store边界：`tests/test_search_suggestion_service.py tests/test_search_suggestion_api.py tests/test_search_suggestions.py`，45 passed。使用合成输入/模型，不证明真实模型质量。
- 受限PG/HTTP授权和恢复：`tests/test_search_suggestions_postgres.py -k 'consent_snapshot or restricted_postgres_http'`，2 passed、63 deselected。此前相关4 passed复用，不重复累计。独占缓存postgres:16-alpine/本机50451合成库已删除，未操作共享库或客户库。
- root装配：新 `tests/test_search_suggestion_runtime.py`，最终6 passed；既有 `tests/test_pilot_runtime.py`15项通过证据复用。前期测试错误使用HTTP被HTTPS门禁拦截，修正测试URL后通过，没有削弱门禁；PG重复使用一次性fixture遇role已存在，改用新独占合成库验证通过，不隐藏环境失败。
- 未变化的模型/process历史测试和桌面包不重跑。无真实供应商调用、用户资料外发、Windows实机、生产部署或客户UAT。

下一接续：复用现有TaskWizard条件编辑器，新增显式生成授权、原请求持久记录和只读核对；结果带依据/未知信息，人工选择采用，绝不覆盖编辑内容。旧 `suggest(profileId, requestId)` 缺草稿版本和授权，不得直接绕接或保留自动外发路径。
