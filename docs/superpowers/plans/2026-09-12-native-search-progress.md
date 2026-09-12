# B站原生搜索页内进度 Implementation Plan

> 使用subagent-driven-development与TDD；按用户要求分文件协作、整批一次非作者review，不重复全量/构包。

**Goal:** 原生B站monitor从实际页内未处理条目接续，并把进度与原文原子入库，不跳过同页剩余内容。
**Architecture:** 原生适配器输出tentative搜索进度；CLAIM冻结服务端head，已签名batch原子CAS提交；沿原journal恢复。
**Tech Stack:** Python/PostgreSQL/FastAPI、Electron TypeScript/Zod、固定MediaCrawler受控runtime。

## Global Constraints

- 基线`f9b4c3514a1d9c8780453290e11e4346d1d24731`，独占worktree`/tmp/yike-v02-scope.Pwf9Fs`，短分支`codex/native-search-progress`；完整V0.2不缩减，无部署/构包/平台实网/模型或外发。
- 本批仅BILIBILI search monitor，adapter=`bili-search-items-v1`，schema=`native-search-progress-v1`；其他3原生平台及评论深翻保留待办。每页page_size=20，最多5篇/原query分配预算，有界评论范围固定`BOUNDED_SAMPLE`。
- 精确请求/回执/游标字段与算法以同日spec的“固定协议”“页内推进与刷新”为共同合同；缺省不添字段，精确整数拒bool/null；旧签名/指纹/恢复不变。新CLAIM `native_progress_version:1`仅CLAIM、与public_sampling互斥；RENEW无进度。
- 下次权威只读服务端已提交head，不读本地marker；物理停止后才能交batch，空batch可推进，未知/取消不盲重试。原文、batch与head同短事务、最终fence保留。
- 私有协商`progressVersion:1`→`?native_progress_version=1`，新响应native_progress:[BILIBILI]仅已有B站monitor policy广告；无协商/once/links不启用。与既有public sampling查询分别调用，不接受组合query。
- 三个任务按文件所有权工作，不覆盖他人改动；实现者不push，root统一冻结commit及一次非作者review。只做受影响定向验证；固定新版patch治理必须核对，旧包不追认。

### Task 1: 服务端协议与原子进度（backend）

**Files:** 新`pilot/native_search_cursor.py`（纯标准库游标校验/推进）、`pilot/native_search_progress.py`（DTO/读写head）；改`pilot/execution_contract.py`、`execution_runtime.py`、`execution_api.py`、`candidate_contract.py`、`candidate_ingestion.py`；必要新migration/runtime grant（自行确认下一个编号）；新`tests/test_native_search_progress.py`及必要原接口测试。不得改app/desktop/vendor/docs。

**Interfaces:** `checked_cursor(value)->dict`严格校验后返回普通dict；`advance_cursor(before, page_ids, processed_ids, has_more)->dict`纯重算，非法抛ValueError；无第三方依赖，供独立平台脚本用importlib加载。CLAIM/batch结构严格按spec，head读写只从真实authority派生scope。候选receipt回显batch.native_progress。

- [ ] 先写RED：旧缺省canonical签名不变；新字段精确/互斥/CLAIM-only，before/after数学、partial page/refresh/empty/repeated IDs。
- [ ] 实现纯函数：CONTINUE计算`consumed=[id for id in page_ids if id in old or id in processed]`；若`len(consumed)==len(page_ids)`，nextpage=page+1当has_more且page<1000，否则1；否则保持page及consumed；refresh_next=true。REFRESH保持page/IDs、refresh_next=false；两路均验证processed是候选前缀，最多5，available非空不得提交空processed。
- [ ] 新head表RLS/ACL/唯一scope，CLAIM只读固定head并持久原receipt，batch检查claim/当前head/revision/base/before/after/query/平台/adapter，原文+batch+head CAS共提交与回滚，保留最终fence。不能依赖received_at排序猜head。
- [ ] 仅自有`yike-research-resources-task1-pg`新隔离库，受限角色/签名/认证HTTP验证0→1→2、空batch、重放固定、已上传未FINISH、并发相同head只一成功、失败回滚/owner/connection隔离；报告未验矩阵。保存仅synthetic request+response到`/tmp/yike-native-progress-http.json`供TS parser。
- [ ] 最小旧合同/API回归，报告`/tmp/yike-native-progress-backend-report.md`；不commit/push或停其他container。

### Task 2: 实际B站受控源与host（source）

**Files:** 新`app/bili_search_progress.py`受控入口；改`app/platform_collection_worker.py`、`app/windows_source_driver.py`、`app/windows_collection_host.py`；必要vendor新patch与lock仅在无法复用受控adapter时使用（先报告root）。新`tests/test_bili_search_progress_runtime.py`及必要host/source测试。不得改pilot/desktop/docs。

**Interfaces:** host请求可选`native_progress:{schema_version:'native-search-progress-v1',adapter_version:'bili-search-items-v1',query,revision,base_batch_request_id,cursor}`；只BILI/search/expected-account有效。host成功输出额外`native_progress`为对应单query delta（query/revision/base/before/after/page_ids/processed_ids/has_more/comments_scope），旧成功frame不变。source_driver输入/返回同字段名，暂存内容在本次私有output目录，不能跨轮直接复用。

- [ ] 先RED，用真实受控方法+合成API响应验证同页20项，每次最多5，下一次取后5；刷新只翻phase不冲掉续读cursor，空页/页内全已处理/末页正确；非法page/aid/numPages、详情或评论失败无checkpoint。
- [ ] 复用现有同浏览器账号guard，安装受控BILI search入口（不得patch运行时文件），query只一次真实`search_video_by_keyword`page_size20/DEFAULT；结果aid唯一、numPages真实校验；所选详情+既有有界comments成功后才能写tentative delta。进度输入只从主进程私有IPC/已验证字段来，禁止日志输出/任意URL或请求。
- [ ] 纯函数动态加载`pilot/native_search_cursor.py`供source脚本，保持直接脚本import不遮蔽runtime config。Windows_source读取完整成功terminal/物理停止/账号确认及tentative delta后返回；失败/取消不返回可提交进度。
- [ ] host绑定query/cursor、限64KiB入/4MiB出，候选正常映射；新增字段受签名batch消费者使用但host不自行签名。一次受影响runtime/host/Windows source定向测试，旧无进度与links无差量。
- [ ] 报告`/tmp/yike-native-progress-source-report.md`、未验Windows/真实平台；不commit/push/构包/平台操作。

### Task 3: 客户端真实贯通（root）

**Files:** 新`desktop/src/shared/nativeSearchProgress.ts`；改shared执行/候选request与receipt schemas，main `executionServicePolicy.ts`、`foregroundCollectionController.ts`、`collectionWorker.ts`、`pythonCollectionDriver.ts`；必要tests。不得代替另两任务改其文件。

**Interfaces:** Cursor/delta严格与spec相同。CollectionDriver completed支持原records数组或新`{records,nativeProgress}`；后者只协商原生CLAIM可用，最终batch.native_progress使用固定claim.request_id/adapter并包含各实际query delta。driver每query传host input，解析返回并重算after；RENEW不能改变冻结CLAIM。新后台receipt应精确对齐原batch。

- [ ] 先RED：旧byte/签名不添undefined、新flag不冒用公共/native别的平台/once，固定私有query；与CLAIM匹配/回复字段遗漏多余均拒绝。
- [ ] 控制器仅B站search monitor协商/传allowNativeProgress，worker CLAIM opt-in并保持初始lease，Python driver逐query使用正式host，输出progress即使records为空。保留过滤前候选预算和原物理停止/未知恢复，不以排除结果数推断游标。
- [ ] 新signed batch经原加密journal→prepare/sign/apply→FINISH；严格schema保留进度，回执逐项匹配；失败结果不可触发新请求补跑。
- [ ] Node24新+受影响Vitest/tsc一次；消费Task1真实本机HTTP产物交正式TS parser；组合controller-worker-host替身验证不是孤立函数。

## 收口

- [ ] 所有产品字节冻结，完整批次独立review；只修具体P0/P1/P2并差量复核；更新唯一证据和taskbook，正常合main/远端SHA回读。未通过整链前不得广告可用或合入半接线能力。

## Evidence

2026-09-12，产品代码`a64bcdaca1e6b906eaf36afa1f7c6b91e7a1f27f`独立整批GO，仅限本批代码合并；未部署/构包/真实平台/外发。上方checkbox保留原实施计划，不作为验收成绩，实际完成与未验范围以本节为准。

- 来源初次RED为adapter缺失（12 failed），之后新源/host链24 passed，包含固定MediaCrawler pin＋仓库patch重建后的真实详情/评论方法与新adapter和账号guard组合。源/host/三平台guard/portable受影响组151 passed、32条件skip（非Windows/无已安装runtime）；后补真实隔离Python进程验证HOST_FILES导入闭包，先因漏带execution_contract RED，再修复GREEN。
- 客户端新模块、driver/CLAIM和controller组合先RED；受影响9文件446 passed、tsc通过。新增严格ID末尾/once拒绝后最小差量37 passed；旧签名固定fingerprint回归在上述受影响组内，没有重跑全仓或构包。
- 后端真实受限PG/本机认证HTTPS产物：`/tmp/yike-native-progress-http.json`（合成账户与业务数据；不含token/signature/signing_payload）。正式桌面`nativeSearchProgress.http.test.ts`消费两次CLAIM、一批candidate回执及Python signing fingerprint，1 passed。运行时设`YIKE_NATIVE_PROGRESS_HTTP_ARTIFACT`为该产物路径；无产物时明确skip，不视为跨语言链路已验。
- Windows固定HOST_FILES补齐adapter、cursor、DTO及执行合同；未改vendor pin/patch，不给旧包背书。cursor只代表搜索条目＋有界评论样本，不代表完整评论树、平台全集或有用商机产量。
- 预算分层按同日spec补充：服务端不能从过滤后batch倒推每query cap；受控driver/host保留过滤前分配，服务端验证前缀、每query上界及真实租约/任务围栏。

- 后台最终66 passed（含7项真实受限PG/本机认证HTTPS），最小旧合同237 passed、1 skipped。首次旧合同重跑因测试DSN缺省用户名错误而setup失败，按自有容器实际用户修正后通过；不属于产品修复。connection-version-only切换新scope的独立端到端场景未另跑，不计为完成。
- 源链最终25 passed，含隔离Python导入闭包；Windows固定清单依赖测试不等于Windows实机运行。各组测试存在重叠，不相加为全仓总数。
- 独立整批初审绑定`5784ec7`，结论NO-GO：两个P2（最新links-capable部署模式误失search进度广告；上一版服务严格拒绝新协商导致旧monitor被阻断）。`a64bcda`修复后独立差量GO，未关闭P0/P1/P2为0/0/0。审核者未参与实现，报告`/tmp/yike-native-progress-independent-review.md`保留首次失败、修复与最终独立探针。
- P2定向证据：能力名单新断言先1 failed，修后2 passed，实际links仍拒绝。读取固定基线`f9b4c35`实际handler的认证路由测试1 passed，生成无凭据产物`/tmp/yike-native-progress-legacy-support.json`；正式ServiceClient消费它，controller先1 failed/4 passed，修后全文件68 passed＋tsc。仅明确422/invalid_request允许一次只读旧能力核对，网络/5xx/其它422/会话变化不降级，执行操作与未知结果不自动重试。

主干收口仅补本节、任务书和整合状态；产品字节保持已审核`a64bcda`不变，正常fast-forward后回读远端SHA，不因文档再跑全套或构包。其它原生平台cursor、评论深翻、公开index外复查、多源研究与真实用户闭环继续，完整Goal保持ACTIVE。
