# 动态公开搜索与原文研究

按现行 AUTHORITY 的 V0.2 自主细化实施授权执行。延续 Codex 开源 Harness，不增加 Agent 框架，不替换专用登录/评论/监测连接器。本批让模型自主搜索后读取命中的原文；仍是内部研究入口，客户 API、持久许可/计费/证据事务和正式部署继续接续，不以本批结束完整 Goal。

## 选择与流程

继续逐站枚举不能扩展未知来源；模型内置联网在当前国产模型协议中不可依赖；采用独立搜索工具＋现有原文工具。使用现有项目已配置的 Serper 搜索接口，固定 `https://google.serper.dev/search`（现有实现和官方公开搜索结果示例可核对），不支持任意转发地址。搜索服务只用于发现链接，不证明采购事实、作者身份或原始发布时间。

`自然语言任务 → Codex 自主生成查询 → search_public_web → 搜索候选 → read_public_page → 实际原文/模型解释分开返回`。

## 合同与保护

- 搜索输入只有 `query`，1–512字符、去首尾/归一连续空白、拒绝控制字符；无调用方 URL、API key、分页、地区或预算参数。每次向供应商发 `{q:query,num:10,hl:"zh-cn"}`，固定 POST/X-API-KEY；不继承代理/Cookie、不跳转、不重试。
- 每任务最多1–10个不同查询，由宿主指定；同查询成功/失败缓存，不重发。先计尝试再I/O，未知不盲重试。截止时间宿主单调时钟，1–1800秒；每搜索最多20秒/1MiB响应。父进程可终止/回收专用搜索子进程；密钥仅经私有stdin进入子进程，不进环境/argv/仓库/日志，关闭阻止新查询并回收已有子进程。
- 搜索成功精确结构：`{status:"SEARCHED",query,observed_at,read_scope:"SEARCH_RESULTS",results:[{url,title,snippet,date_hint,rank}],omitted_count,replayed}`。至多10条唯一、安全匿名HTTPS结果；title≤1000、snippet≤2000、date_hint null或≤200字符，rank正整数，缺失文本/日期为null。`omitted_count`记录被排除的供应商结果，不声称全网总量。观测时间为带时区ISO，不刷新需求时间；date_hint始终只是索引提示。
- 失败精确结构 `{status:"FAILED",code,replayed}`，code限 `invalid_query/unavailable/auth_failed/rate_limited/timeout/too_large/invalid_search_result/search_limit_reached/deadline_exceeded/closed`。失败、零结果、缺失/畸形 organic 区分；只有合法 organic 空数组可表示空搜索。
- 复用现有临时有令牌 loopback bridge，新增可选 `/v1/public-search`，POST体只含query；无搜索服务时404。搜索密钥由宿主 `PublicSearchSession` 持有，模型和MCP只收到随机临时令牌、明确loopback地址。`ResponsesBridge.__exit__`关闭可选搜索会话。原模型请求计数与搜索尝试分别记录，不混作计费。
- MCP只在明确配置searcher时增加 `search_public_web`，结果仍精确验证。此模式下原文只读本轮实际搜索命中的URL，不允许模型把任意URL假装搜索命中；旧read-only模式不改变。搜索摘要和原文分别存放；不得复制摘要生成READ证据。
- 新增 `run_public_research_mission`，旧 `run_public_read_mission` 返回兼容。新模式返回旧字段＋`searches/search_failures`，成功须实际 SEARCHED 与 READ 及turn.completed；无可核验原文返回固定 `no_verified_reads`，保留搜索观察，不能把它解释为供应商故障或“全网无需求”。错误/取消保留已观察事实与未知请求记录。保持既有字节/时间/子进程/允许工具界限。

## 验证

定向 RED/GREEN 覆盖搜索结构、空结果、失败、限额/缓存/取消/进程密钥隔离、MCP授权及只读命中来源、实际Codex JSONL分流和旧read-only兼容。一次小规模真实中文查询→模型工具读取，显示原始时间待核、不是合格商机。独立整批审核一次，真实发现修复仅差量复核；不重复全套/构包/模型调用。密钥缺失或不可用时如实保留阻塞，不伪造结果。
