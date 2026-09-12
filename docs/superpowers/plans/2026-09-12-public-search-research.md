# Public Search Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Repository instruction replaces repeated per-task reviews with one independent whole-batch review.

**Goal:** Codex selects queries, searches real public sources and reads discovered originals without turning snippets into evidence.

**Architecture:** Fixed Serper search session on host; subprocess-bound request and private stdin key; existing authenticated loopback bridge exposes optional search route. MCP gets only temporary URL/token; new research worker records search observations separately.

**Tech Stack:** Existing Python/httpx/MCP/Codex, stdlib search child; no added dependency or production activation.

## Global Constraints

- Design `docs/superpowers/specs/2026-09-12-public-search-research-design.md` binds exact fields/statuses/bounds. Fixed https://google.serper.dev/search, POST `{q:query,num:10,hl:"zh-cn"}`, X-API-KEY, no arbitrary forwarding/proxy/redirect/retry.
- Query1–512 chars, max_searches1–10, task1–1800seconds, each search20seconds/1MiB; host limits only. Keys never argv/env/repo/logs; provider subprocess stdin only. Random temporary loopback token is not a provider credential.
- Search results are SEARCH_RESULTS observations, not original posts, verified buyers, dates or approved leads. Preserve empty-vs-failed and omitted_count; max10safeuniqueHTTPS URLs. Only actual discovered URLs readable in new search mode; existing read-only behavior remains.
- No login/sending, DB/customerAPI/persistentbudget/deploy; no personal Codex settings/keys inherited. One review, affected tests only. Same-source/same-query repeats never inflate facts.

### Task 1: Bounded search session and result contract

**Own files:** create `pilot/public_search.py`, `pilot/public_search_worker.py`, `tests/test_public_search.py` only.

**Interfaces:**
```python
normalize_query(query: str) -> str  # ValueError('invalid_query') fixed only
valid_search_result(value: dict, query: str) -> bool
class PublicSearchSession:
    def __init__(self, *, api_key: str, max_searches: int, deadline: float): ...
    def search(self, query: str) -> dict: ... # exact SEARCHED/FAILED design structure
    def close(self): ... # idempotent, stop new work and terminate/reap owned children
```

- [ ] Write failing contract tests: canonical query caching,10resultcap/urlnormalization/dedup/omitted_count, nullablehints, awareobservedtime, malformedorganic≠empty, fixedfailurecode, boundedfieldvalues. Example assert `session.search(' 中文   需求 ')['query']=='中文 需求'` and result read_scope SEARCH_RESULTS, not READ. Fake low-level HTTP in child module only for deterministic response parsing, not returning whole fake domain service.
- [ ] Write missing-module/behavior RED with `uv run --frozen --extra dev --extra research pytest -q tests/test_public_search.py`. Add real fixture-process deadline/close tests and inspect synthetickey absentargv/env; receiveskey onlystdin. Test concurrent samequery consumes one attempt and closing prevents spawn race.
- [ ] Implement session serial/cache/count reservation with own active-process lock and close flag; do not reuse global READS_STOPPED. Spawn isolatedPython worker `-I` with env{} and private stdin `{query,api_key,timeout_seconds}`; child stdlib HTTP fixedendpoint, headerkey, 1MiB body cap and no rawerror. Child response exact `{ok:true,result}` or `{ok:false,code}`; parent validates result and limits, kills/reaps at min(20,deadline-now). Payload/output bounded; child network data cannot echo key into result. No test-only public methods.
- [ ] GREEN targetedfile, diffcheck, commit only owned files. Report RED/GREEN/commit/remaininglimits, no live provider or credential reads by this agent.

### Task 2: Codex research mode and actual-event bookkeeping

**Own files:** `pilot/codex_research_worker.py`, `tests/test_codex_research_worker.py` only.

**Consumes Task1:** PublicSearchSession(api_key,max_searches,deadline), normalize_query, valid_search_result.
**Consumes root:** ResponsesBridge optional `search_service=None` constructor, `.search_url` URL orNone; existing token. MCP env accepts `YIKE_PUBLIC_SEARCH_URL` and `YIKE_PUBLIC_SEARCH_TOKEN` only when enabled. MCP tool name `search_public_web`; namespace same `mcp__yike_public`. Root owns gateway/MCP implementation.
**Produces:**
```python
run_public_research_mission(description: str, *, codex_binary: str, python_binary: str,
                           api_key: str, model: str, search_api_key: str,
                           max_searches: int = 3, max_reads: int = 5,
                           max_requests: int = 8, max_seconds: int = 120,
                           cancelled=lambda:False) -> dict
# oldresultfields + searches:list[SEARCHED], search_failures:list[{query,code}]
```

MCP 仍由 `/usr/bin/env -i` 启动；临时 `YIKE_PUBLIC_SEARCH_URL=...` 与 `YIKE_PUBLIC_SEARCH_TOKEN=...` 作为 env 命令赋值参数传入，随后是独立 Python 命令。不使用会被 `env -i` 清掉的 `mcp_servers.yike_public.env`；这里仅含随机临时令牌，绝不含供应商密钥。研究模式指令写明宿主本次搜索、读取、模型请求上限，并要求为最终答复留出预算；优先买方业务行动和社区原生内容，不内置行业或域名允许名单。

- [ ] RED actual JSONL fixtures: real `mcp_tool_call` server yike_public/tool search_public_web/argumentsquery/result.structured_content plus read; invalidsearchschema/foreignurl/duplicateID conflict rejects; modeltext alone notsearch, valid searchzeroresults retained with no_verified_reads. Old read-onlyfixtures keep exact resultshape and originalmission semantics.
- [ ] RED subprocess config checks: provider andsearchkey absent env/argv/cwd/prompt; onlytemporaryURL/token passedMCP env. New mode allowstwofunctions and instructions explicitly search thenread; oldmode nosearch. Snapshot providerrecords aftercleanup, close search session even onspawn/enter/error/cancel. Reject key substrings inpublicdescription.
- [ ] Implement shared internal runner conservatively, preserve public oldfunctionsignature. Search events use Task1validator, dedupactualeventIDs; readURLs mustbelongto actualcompletedsearchresults in newmode. Finalcode no_verified_searches if no actualSEARCHED, no_verified_reads if search butno original. Source/modeltext remainseparate, no autonomousretry/leadapproval.
- [ ] Targeted changedfile GREEN (may wait for Task1 imports; no fakeproductionstub), diffcheck, commitownedfiles; report tests/commit/concerns. No realprovider/keyaccess byagent.

### Task 3: Loopback and MCP integration (root)

**Files:** `pilot/responses_bridge.py`, `pilot/research_tools.py`, new `pilot/search_tool_client.py`, corresponding tests, `docs/RESEARCH_TOOLS.md`.

- [ ] RED live loopback route: unauthenticated/unknownroute disabled, exactquerypayloadonly, no modelquota consumed, serviceclose oncontext exit, safeerrors. Bridge optionalservice drives exact `/v1/public-search` after existing Bearer/sizevalidation, responsevalidatedfixedcontract; defaultbridgeunchanged.
- [ ] RED MCP officialsession advertisessearch only opt-in, successful SEARCHED adds allowedreadURLs; only original reader can return READ; searchfailure emptydistinct; URL/tokenconfiguration mustbe fixedloopbackhttp with exactpath and numericport, no userinfo/query/fragment, not publicarbitraryrequest. `search_tool_client` POST uses httpx trust_env=False/no redirects, boundedresponse, fixederrorcodes. Credentials onlytemp token fromhostenv.
- [ ] Implement and run only affectedtests including old MCP/bridge regressions; no fullsuite/build. Existing hardwatchdog/reader cleanup retained.
- [ ] One tiny authorized real Codex/Ark/Serper mission from existing keys loadedinprocess, public Chinese query only, ≤2searches/2reads/5modelcalls/90sec. Report actualurls/time/status, snippets notbuyerfacts; failedsources notno-demand.

### Task 4: Independent review and integration

- [ ] Freeze code SHA, generate reviewpackage, freshindependentreview; fix realfindingswithnarrowtests/deltareview only.
- [ ] Update single evidence section/taskbook, fetch/preserveconcurrentmain, merge/push/verifyliveparity. Goal remainsfullACTIVE; thisisresearchcapability, notall-platform/production/customerproof.

## Evidence

代码候选 `0cc4827`，基线 `f9fc299`；独立整批审核进行中。旧只读批次不重复验收。当前没有客户 API、持久预算、数据库证据入库、部署或合格商机交付证明。

- 搜索后端：定向25 passed。执行器：补充 None 模式与重放去重、动态额度指令后37 passed /16.05秒。根集成：20 passed；旧 MCP/桥接受影响回归53 passed /16.98秒。均为协议/实现证据，不是商业效果。
- 首次整合诊断：2次真实搜索、18个索引候选，两个原文分别 invalid_url/unavailable；模型在额度用尽后仍尝试追加调用，最终 runtime_failed，23.41秒。没有成功原文、没有合格线索。此次工作树仍有并行修复，不绑定为冻结候选验收。由此追加明确额度指令与买方/社区优先策略，保留安全读取限制。
- 改动后固定 `0cc4827`：2026-09-12 15:57:48–15:58:03 UTC 实际搜索/读取，整次38.80秒，COMPLETED；2次搜索18个候选、2次原文成功、5次真实模型请求，零读取/搜索失败。Codex 自主查询 `V2EX 求开发 AI工具 委托 定制` 与 `V2EX 找人开发 企业知识库 RAG 外包`。这次任务显式偏好 V2EX，是受控社区样本，不证明跨平台覆盖。
- 实际原文：[行业知识库预算讨论](https://www.v2ex.com/t/1155193)，4343字符，SHA256 `ca41f764d638bed862bfa19f26a0245a8171bd1b6f37ddbdee7ec93ff09dd586`；[AI客服合作/外包帖子](https://www.v2ex.com/t/1197102)，1492字符，SHA256 `94ce8ec83155c1df996066d1698868d06ca9c2c9c927f9414789b38a4bd7a89b`。索引分别提示2025-08-27与2026-03-10，均不能当本轮近期有效线索；未完成作者原始日期与当前开放状态人工复核，不计净新增，不触达。
- 该次 CLI 用量 input29809、cached input14760、output1062；5个供应商请求分别 input/output为3069/64、4149/66、5304/67、8121/67、9166/798。字段按来源保留，不是人民币费用或已定义搜贝换算。
- 已验证本地既有 Serper 与 Ark 凭据的本轮真实调用；密钥只在宿主内存读取，没有复制入仓库/参数/日志。Qwen 仍只有配置位置线索，未实际调用，不评选模型优胜者。

接续：将通用执行器接入已确认行业策略、需求时效/排除项、现有许可与证据事务及客户进度；专用登录/评论/监测连接器继续保留。技术链完成不能替代“近期且值得联系”质量门槛。前端同步调整参见本次体验审查，不等待所有后端功能完成才联调。
