# 内部公开原文工具

这是研究 Worker 的工具，不是客户服务地址，也不是全网搜索已经接通的声明。客户只登录意客；模型密钥与工具配置由服务端持有。

## 当前入口

安装可选工具依赖（不强升现有 Web 依赖）：

```sh
uv sync --frozen --extra research
uv run --frozen --extra research python -m pilot.research_tools --max-reads 5 --max-seconds 60
```

第二条命令启动标准 MCP stdio 服务，供父级研究 Harness 通过 stdin/stdout 使用，终端等待输入是正常状态。不会监听 HTTP 端口，不读取平台 Cookie、Codex 登录态、业务数据库或模型密钥。宿主应使用独立环境启动，不把主服务凭据传给工具进程。

默认只有 `read_public_page({"url":"https://example.com/"})`：返回实际提取的标题/原文、读取时间、文本SHA256、读取范围 `PUBLIC_PAGE_TEXT` 与 `UNREVIEWED` 标识。读取不是事实核验或需求判断，不自动提取/断言作者和发布日期。宿主明确启用下述搜索模式后增加搜索工具；两种模式均没有登录、写库、审批或发送能力。

`max-reads`（1–100）与 `max-seconds`（1–1800）由宿主指定，工具参数不能修改。尝试前计数，同URL成功/失败本进程内缓存重放；多个请求串行处理。进程重启后的持久去重和任务预算仍必须接现有账本，不能依靠此缓存结算搜贝。

## 读取边界

- 仅匿名 HTTPS/default443，支持正常公开域名，不要求加入网站目录。
- 拒绝私网DNS和常见凭据查询参数；固定已验证IP连接并保留原域名TLS验证；无代理、Cookie、跳转或自动重试。
- 每页最多20秒（包括DNS），1MiB响应正文、60,000字符提取文本；超限/超时明确失败，不截取后声称完整。
- UTF8/ASCII HTML或纯文本。HTML脚本、样式及可识别隐藏节点不计正文；不是浏览器渲染，不能保证CSS可见性、登录后内容或动态评论完整性。
- `observed_at`只是本次读取时间，不刷新需求原始时间。
- 读取子进程使用隔离Python和空环境；超时或中断回收子进程。仅固定错误码进入协议，不输出底层异常正文。

专用连接器保留：登录、评论展开和增量监测优先复用已有平台连接器及有效缓存；通用研究用于扩展未知来源。专用路径减少重复浏览和模型操作的潜力需以实际用量验证，不预先承诺节省比例。

## 验证与接续

### 内部 Codex 执行入口

`pilot.codex_research_worker.run_public_read_mission` 使用明确指定的 Codex 可执行文件和安装本包的 Python；适用 POSIX 服务端，不是 Windows 客户端执行器。宿主在内存中传入模型密钥、模型名、公开阅读任务和资源上限。当前适配仅固定火山方舟 Responses 地址，不支持调用方指定任意模型服务地址；Qwen 尚未实测或启用。

```python
from pilot.codex_research_worker import run_public_read_mission

result = run_public_read_mission(
    "用提供的工具读取 https://example.com/，仅依据原文说明标题。",
    codex_binary=approved_codex_path,
    python_binary=research_python_path,
    api_key=secret_from_host,  # 宿主凭据存储提供；不得写入任务文本或日志
    model=approved_model,
    max_reads=1, max_requests=2, max_seconds=60,
    cancelled=host_cancelled,
)
```

内部临时桥接器只监听带随机令牌的本机端口，将 Codex 的命名空间工具协议转换为供应商兼容形式。真实供应商密钥只留在桥接器内存，不进入 Codex 参数、工作目录或工具环境。执行器使用临时工作区、独立 Codex 状态目录、禁用用户配置和无关工具；这不替代正式部署时逐租户容器和网络隔离。

返回 `COMPLETED/FAILED/CANCELLED`、固定错误码、实际 MCP `reads`、`read_failures`、独立模型 `summary`、Token 用量和供应商请求回执。模型自述不生成原文证据；没有成功工具读取则不能完成。失败/取消可保留此前已读取事实，但仍是失败/取消，缺失用量保持未知。不得直接把模型摘要发布为已复核商机。

此入口尚未绑定客户 API、持久任务许可、搜贝账本或数据库证据事务，不能由客户直接调用，也不等于全网搜索已经接通。任务限制是本次执行保护，不是跨任务配额或计费依据。当前实现及真实调用证据见[执行器批次记录](superpowers/plans/2026-09-12-domestic-harness.md#evidence)。

```sh
uv run --frozen --extra dev --extra research pytest -q tests/test_open_web_reader.py tests/test_research_tools.py
```

协议测试使用官方SDK真实会话和stdio子进程；网络替身仅用于可重复的故障/边界测试，不算真实需求。未安装research依赖时协议测试显式跳过。

后台优先接Codex开源Harness与国产模型API，但工具协议不依赖模型品牌。旧读取工具证据集中在[读取批次](superpowers/plans/2026-09-12-open-web-research.md#evidence)。后续仍须完成 Skill 多轮业务研究、现有签名任务/许可/证据事务、客户进度和真实效果验证；不得用本工具取代这些交付。

### 自主搜索后读取

新增内部 `run_public_research_mission`，参数沿用只读入口并增加宿主内存中的 `search_api_key`、`max_searches`（默认3）。默认最多5次读取、8次模型请求、120秒。模型只能调用 `search_public_web` 和 `read_public_page`，搜索使用固定 Serper 服务；搜索进程通过私有 stdin 接收供应商密钥，MCP 只持有临时本机端口与随机令牌。

```python
from pilot.codex_research_worker import run_public_research_mission

result = run_public_research_mission(
    confirmed_public_mission,
    codex_binary=approved_codex_path,
    python_binary=research_python_path,
    api_key=model_secret_from_host,
    model=approved_model,
    search_api_key=search_secret_from_host,
    max_searches=2, max_reads=2, max_requests=6, max_seconds=90,
    cancelled=host_cancelled,
)
```

结果新增 `searches` / `search_failures`，索引摘要、索引日期提示和原文证据分开。搜索模式只允许读取本轮实际命中 URL；同查询缓存不会算新发现。搜索空结果与搜索失败分开；无实际原文不得完成，返回 `no_verified_searches` 或 `no_verified_reads` 等固定错误码。读取边界仍如上，不额外支持跳转、JS或登录。

COMPLETED 仅表示执行器正常结束并取得搜索和原文，不表示近期、匹配、已复核或可联系。任务时效、行业判断、持久许可、客户隔离与证据入库仍需通过产品链路接入。一次真实成功及前次失败集中在[搜索批次证据](superpowers/plans/2026-09-12-public-search-research.md#evidence)，不得把这些旧帖作为新线索推给客户。
