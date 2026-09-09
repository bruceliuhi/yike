# 04B 原文搜索建议后台组件：Win → Mac

日期：2026-09-09。这是独立组件交接，不是完整 HTTP/客户端功能或 Mac 已接收 ACK。唯一状态见[任务书](../V02_IMPLEMENTATION_TASKBOOK.md)，验证和失败历史见[后台验收](../qa/V02-04B_SEARCH_BACKEND_WIN_REVIEW.md)。

## 本批可审查组件

- `e26c7a3`：严格跨行业模型适配器。输入业务介绍，输出可编辑词、排除词、理由、逐字原文依据和未知项；模型专项187通过，不是实际供应商质量。
- `a8707a8`：`ProcessSearchSuggestionModel`，Windows实际子进程总截止/有序关闭，独立17专项通过。正文与凭据仅stdin；同包固定worker，不携带数据库/代理配置；不是任意命令执行器。
- `32c70dd`：`SearchSuggestionStore`、110迁移和最小grant；最终98相关测试通过（35纯＋63真实PG），原文摘要/证据/usage、用户/租户隔离、配额及原回执持久化。独立质量发现的成员角色超权已通过真实反例修正并复审。

本批根代理整合模型/进程/纯请求239通过；没有把替身、组件或通过数当成客户试用闭环。

## 固定消费边界

```python
request = SearchSuggestionRequest(request_id=request_id, draft_id=draft_id,
                                  profile_version_id=profile_version_id, draft_revision=draft_revision)
receipt, description_or_none = store.reserve(claims, request, provider=provider, model=model)
receipt = store.finish(claims, request_id, content=content, usage=usage)
receipt = store.finish(claims, request_id, error=model_error)  # SearchSuggestionError
receipt = store.finish(claims, request_id, error="dispatch_failed")  # 确认未调用才使用
receipt = store.get_receipt(claims, request_id)
```

三个ID是规范小写UUID；revision是0..2147483647严格整数。身份仅来自现有SessionRegistry；客户端不能指定tenant/user/description/model/费用。重放绑定完整原请求，不返回description、不因模型配置变化重复调用；新会话可读同用户历史，但只能原仍有效会话完成该请求。

安全回执只有 `request_id/draft_id/draft_revision/profile_version_id/profile_sha256/rule_version/model_provider/model_name/state/result/usage/error_code/created_at/updated_at/profile_current`。state为PENDING/SUCCEEDED/FAILED/UNKNOWN；profile_current是当前读取的画像状态，不是执行许可。规则版本、结果及usage按原请求保存，不生成strategy_version_id或APPROVED商机。

配额是工程保护：同租户10次/滚动小时、新请求至少间隔2秒；跨用户汇总，FAILED/UNKNOWN仍计数，重放不新增，不代表搜贝或商业定价。完成时重新核对原画像及逐字依据；画像变化为FAILED/profile_changed，会话失效不披露/覆盖，保留原PENDING待核对，不自动重派。

`ProcessSearchSuggestionModel`与原模型generate接口相同，另有`available`和`close(timeout_seconds=5)->bool`。明确未创建worker抛`SearchSuggestionProcessUnavailable`，后台应映射为`error="dispatch_failed"`，不能直接把该异常对象传给store.finish；不确定调用使用固定SearchSuggestionError/UNKNOWN。close=False表示退出未确认，不能假装释放资源或继续准入。

## 分工与尚不能启用的部分

Mac `639b17d`已确认111用于执行切片、避开Win110；108继续留资料。Win不改 `pilot/db.py`、`pilot/ui_api.py`、`pilot/web.py`或`pilot/store.py`；110尚未加入默认迁移注册。将来Mac串行集成时注册版本键`v02-search-suggestions`及`110_v02_search_suggestions.sql`，在受信迁移环境执行独立grant，不把管理凭据注入客户端/模型worker。没有要求Mac此刻启用search_suggestions。

Win继续交付：最多4任务准入/2执行的持久请求后台与认证router → 既有05C页面/原请求ledger → 最终策略版本、预算和Mac同事务resolver → 真实“多找类似”。2026-09-10已正常合入Mac `d6c75c7`至`093bd7d`，保留111执行、112候选及113判断认领；Mac当前接续04C，Win不重复这些后台或R4页面。实际执行[契约](../contracts/V02_EXECUTION_RUNTIME.md)的 `strategy_resolver(cursor, claims, profile_version_id, strategy_version_id)` 返回 `ConfirmedExecutionStrategy`，须在同一短事务核验完整确认snapshot/hash，不可复用旧UI v1配置hash或拿建议request_id冒充策略；此resolver尚未交付，不能启用真实任务。

外发授权快照仍需Win随服务接入实现：用户明确看到并确认实际发送的业务正文和实际接收方，绑定原请求、正文摘要、用途、受控提供方配置/模型版本与确认时间；`openai-compatible`只是协议名称。确认画像不自动允许所有文本外发。授权/版本变化与派发顺序需明确，已可能外发不能承诺撤回。此项未完成前默认能力继续关闭。

父进程硬崩溃孤儿清理、其他OS实测、真实模型质量、最终策略/真实来源/触达及Windows客户试用仍未验收。原文证据、多找类似、短句建联三项首发门槛均保留，整体Goal与04B继续IN_PROGRESS。
