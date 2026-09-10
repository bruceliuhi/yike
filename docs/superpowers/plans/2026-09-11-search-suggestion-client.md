# 搜索建议客户端接续

Base `1b47121a73fe15c4aa1787ea415d9ee6247a191b`。执行已批准04B/05C及[已接通服务](2026-09-11-search-suggestion-service.md)。复用现有TaskWizard/Modal/TermEditor，不重做布局。通过真实固定API接建议，不自动外发业务介绍，不自动采用，不把建议当执行策略。只做受影响测试、一轮独立整批审核和一次renderer候选构建；无实际模型外发。

## Task 1：普通客户端生成、恢复、人工采用

- [ ] 工作树 `/tmp/yike-v02-scope.Pwf9Fs`，仅改 `desktop/src/renderer/pages/TaskWizard.tsx`，新增 `pages/tasks/SearchSuggestionPanel.tsx`、`pages/tasks/searchSuggestionStorage.ts`（必要可加同目录hook）及对应独立测试。root负责shared/API/services/contracts接线，不改彼此文件。先RED再实现，不派生更多代理。
- [ ] root提供 `services/searchSuggestions.ts`：`SearchSuggestionsService.preview(profileVersionId):Promise<SuggestionPreview>`、`.submit(request:SuggestionRequest):Promise<SuggestionReceipt>`、`.getReceipt(request:SuggestionRequest):Promise<SuggestionReceipt>`。类型和schema从 `shared/searchSuggestions.ts` 导出。
- [ ] `SuggestionPreview`字段：profile_version_id、profile_sha256、description、model_provider、model_name、disclosure_policy_version固定profile-description-v1。`SuggestionRequest`为request_id/draft_id/profile_version_id/draft_revision及disclosure对象（accepted:true,profile_sha256,model_provider,model_name,policy_version）。`SuggestionReceipt`有上述原请求四项、profile_sha256/model_provider/model_name/disclosure_policy_version、rule_version固定search-suggestion-v1、state PENDING/SUCCEEDED/FAILED/UNKNOWN、profile_current:boolean、result:null或{keywords,exclusions,rationale,evidence,unknowns}、usage:null或token计量、error_code、created_at/updated_at。adapter对原绑定严格校验，UI不能用as替代动态校验。
- [ ] 现有 `YikeService.searchSuggestions?` 接真实服务。当它存在时，TaskWizard不再自动调用旧suggest；点击生成只读取预览，展示完整业务介绍、模型信息和将其发送给受控模型的用途，用户明确确认后才POST。没有有效登录/客户空间/确认画像/规范草稿ID时拒绝生成，手工词仍可编辑。前端不增加自由模型地址或凭据。
- [ ] 同一用户+客户空间+版本在本机只保留一个未解决建议请求（包含原草稿和画像绑定），使用独立持久localStorage命名空间，不被clearLocalDrafts抹掉。提交前可靠写入和回读；失败不POST。未知/PENDING不能新UUID重试；刷新/重开只GET原请求。不同草稿/画像可以显示历史原请求只读核对，不把历史建议采用到当前草稿。记录损坏/不可写须明确错误，不当成空记录。严查存储身份/绑定且清理仅原条目；scope变化不能清除旧scope记录或把旧结果套给新用户。
- [ ] POST快速返回后有界GET轮询（总等待最多45秒，正常轮询间隔至少1秒；每次请求也有限时），取消只停止本地等待，不宣称撤销模型或费用；保留原记录供“核对原请求”。刷新不POST，按钮连点不重复POST。未收到/无法核验的原回执保持未知；404不推断未执行，不自动重新提交。服务/身份/组件卸载改变后迟到响应不能打开旧确认/预览或改当前draft。
- [ ] 成功结果显示关键词/排除词、依据、未知信息和建议原因。采用前重新GET原回执确认profile_current且原绑定一致；仅当前原草稿/画像可采用，过期结果仍可读历史。用既有applySuggestion对当前draft合并新增/替换未修改AI项，人工新增/编辑/删除全部保留，平台与日程不变；超20词拒绝写入。生成期间编辑不会被覆盖；不要求用户停止手工编辑。
- [ ] 只有明确终态可结束原请求记录并开始新的授权流程；UNKNOWN/PENDING仅核对不重试。用户拒绝采用/保留当前时可结束已验证终态，不删除未解决请求。结果不自动生成strategy id、采集或发送。旧注入测试服务没有searchSuggestions时可保留旧兼容流程，普通真实client必须走新路径。
- [ ] 定向UI/存储测试：挂载不外发、显式确认一次、存储失败不发、超时/刷新仅原GET、人工修改/删除保留、scope/画像切换迟到无效、过期不能采用、原请求恢复到正确草稿。复用已有TaskWizard测试，只跑新路径+受影响旧用例，避免全套。依赖root会链接desktop/node_modules；Node `/Users/xingheimac/.nvm/versions/node/v24.19.0/bin/node`。Vitest/tsc必须cwd worktree/desktop，DEBUG_PRINT_LIMIT=1000。
- [ ] 仅提交所属文件，不push。简报到绝对私有git-dir/sdd/search-suggestion-client-ui-report.md，说明SHA/命令/失败/未验范围。不得写产品目录sdd。

## Task 2：固定API与原绑定校验（root）

- [ ] shared严格请求/回执schema、固定IPC操作suggestions.preview/submit/receipt和路径映射；受认证传输复用requestRaw，不引入自由HTTP。
- [ ] 新typed adapter验证预览profileId和回执完整原request/profile/draft/revision/hash/model/policy；状态/结果/错误一致，不把其他请求成功套入当前。
- [ ] root接普通client与YikeService；定向schema/adapter/主进程策略测试、最终tsc及一次renderer build。独立整批审核通过再同步main。
- [ ] 本批无实际供应商效果、Windows包/实机、生产或跨行业UAT，完整Goal保持active。

## 实施与验证

初审源码 `083db0f8f0140993744447d853a23149d4d6787e`，整批基线 `1b47121`；固定传输 `9c4ac5b`、界面主提交 `a9f8fe4`。独立审核发现两项P2：损坏原请求可被新写覆盖；用户结束请求后迟到采用仍可能修改草稿。两项修复和增量复核前不得集成；候选不等于发布。

最终源码 `e751377de9314196707968efe2c69303aaf0123b`，两项P2已修并经非作者增量复核GO。损坏/异请求禁止覆写、结束使迟到采用失效；3条回归先RED后通过，最终45项相关UI/存储/TaskWizard检查及tsc通过（包含原42，不累计）。最终源码只执行一次 `vite build --config vite.renderer.config.ts` 成功；这是renderer产物，不是Windows安装包或实际供应商验收。

入口：新建单次采集或持续监控任务的“搜索条件”。真实服务存在时不再自动调用旧suggest；点击“生成建议”只读披露预览，确认后才提交业务介绍。结果展示依据/未知项，采用前重查原请求；手工新增/修改/删除保留。取消仅停止本地等待，PENDING/UNKNOWN和404不自动重发；独立持久记录不会被清空普通草稿抹掉。

- `tests/searchSuggestionsTransport.test.ts tests/servicePolicy.test.ts`：16通过；取消信号增量单项通过，其余12项未重跑不重复累计。固定IPC拒绝自造地址、身份与额外字段，回执校验原草稿/画像/版本/摘要/模型/授权。
- `tests/ui/search-suggestion-storage.test.ts tests/ui/search-suggestion-panel.test.tsx tests/ui/task-wizard.test.tsx`：42通过；`tsc --noEmit`、`git diff --check`通过。
- 中间失败保留：首次新模块缺失RED；UI合成画像ID不符合规范UUID、新增AbortSignal后测试断言未带第二参数，修正测试后通过。共享工作树一次并发amend影响提交划分，root已比对确认取消传输字节未丢；后续仅root串行提交，审核按完整基线差量、不按HEAD~1。
- 不重复上一批后台/模型/PG测试；尚未实际调用供应商或上传业务资料、未生成Windows安装包、未实际平台/生产/UAT。不把合成UI或前端构包作为真实采集或商业效果。

后续：从新确认画像出发，在授权环境完成真实模型建议→人工改词→确认策略→三平台任务→候选复核的同版本主流程验收；继续完整V0.2的平台和客户交付，不重做已经接通的搜索建议服务及页面。

保守恢复边界：提交报错但没有可核验终态时，当前保留原请求；仅GET404不会解锁。后续需补服务端绑定的“明确未受理”证据，改善配额/授权变化等请求的恢复体验，不靠客户端猜测未执行。
