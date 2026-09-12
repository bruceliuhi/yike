# 内部公开原文工具

这是研究 Worker 的工具，不是客户服务地址，也不是全网搜索已经接通的声明。客户只登录意客；模型密钥与工具配置由服务端持有。

## 当前入口

安装可选工具依赖（不强升现有 Web 依赖）：

```sh
uv sync --frozen --extra research
uv run --frozen --extra research python -m pilot.research_tools --max-reads 5 --max-seconds 60
```

第二条命令启动标准 MCP stdio 服务，供父级研究 Harness 通过 stdin/stdout 使用，终端等待输入是正常状态。不会监听 HTTP 端口，不读取平台 Cookie、Codex 登录态、业务数据库或模型密钥。宿主应使用独立环境启动，不把主服务凭据传给工具进程。

只有 `read_public_page({"url":"https://example.com/"})`：返回实际提取的标题/原文、读取时间、文本SHA256、读取范围 `PUBLIC_PAGE_TEXT` 与 `UNREVIEWED` 标识。读取不是事实核验或需求判断，不自动提取/断言作者和发布日期。工具没有搜索、登录、写库、审批或发送能力。

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

```sh
uv run --frozen --extra dev --extra research pytest -q tests/test_open_web_reader.py tests/test_research_tools.py
```

协议测试使用官方SDK真实会话和stdio子进程；网络替身仅用于可重复的故障/边界测试，不算真实需求。未安装research依赖时协议测试显式跳过。

后台优先接Codex开源Harness与国产模型API，但工具协议不依赖模型品牌。已确认通过的运行与失败记录集中在[本批证据](superpowers/plans/2026-09-12-open-web-research.md#evidence)。后续仍须完成实际搜索工具、Skill多轮研究、现有签名任务/许可/证据事务、客户进度和真实效果验证；不得用本工具取代这些交付。
