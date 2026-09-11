# 当前邀请包的实际执行边界

2026-09-11；固定源码/线上 customer `fbf9f942df0c2be2189a98a930948f9f9b104b1b`。本记录说明已核对的装配边界，不升级产品范围，不修改生产配置，不替代客户验收。

## 重要结论

**当前 Mac arm64 邀请包不是完整四平台获客执行版。** 能启动、显示登录页和连上服务，不等于能够在 Mac 运行四平台采集。用户已明确暂时没有 Windows 环境；不得继续把 Windows 专属路径交给 Mac 用户验收。

| 当前功能 | 装配事实 | 验收边界 |
| --- | --- | --- |
| 客户登录、画像、业务资料、服务端判断/复核/草稿/跟进 | 使用固定 HTTPS 服务，不依赖 Python 平台运行时 | 登录表单/匿名连接已验；实际客户登录、资料和后续流程仍需真实操作验证 |
| 小红书、抖音、B站、知乎连接和采集 | Mac 正式包未装配原生 runtime/controller | 不能在此包验收或宣传已支持；页面存在不改变此限制 |
| 原生平台发送、回复读取 | 同样由原生 runtime 装配 | Mac 此包不可用；发送还需独立对象/内容确认 |
| 匿名公开社区采样 | 主进程 controller 独立于 Python，可由匹配服务模式提供 | 当前生产只设置 four-platform-monitor-v1，公开来源未启用；不能当作现已可用的替代闭环 |
| Windows 完整原生执行 | 专属 portable payload 与 bootstrap 路径已开发 | 缺本轮同源产物和实机环境；Mac 证据不代替 Win |

## 直接源码与运行依据

- `desktop/src/main/platformLoginConfiguration.ts`：`packaged || platform!=='win32'` 返回 null。临时开发环境配置不是 Mac 正式包运行入口。
- `desktop/src/main/main.ts`：只有 `app.isPackaged && process.platform==='win32'` 装配 portable bootstrap；`attachPlatformRuntime` 才创建平台登录、原生采集、发送和回复 controllers。未装配时平台连接返回 SERVICE_UNAVAILABLE，发送/读取返回失败。
- 同文件在没有 Python/runtime 时仍创建匿名 foreground/monitor controllers；这是匿名来源的技术基础，不是自动开启服务端能力。
- `pilot/foreground_collection.py`：`four-platform-monitor-v1` 只提供账号平台；`four-platform-public-monitor-v1` 才提供 V2EX 单次采样，`four-platform-public-sampling-monitor-v1` 另加定时抽样。它们均不代表全站搜索或足量商机。
- root 本次 SSH 只读核对：customer revision 为 fbf9f94、running；唯一读取的非秘密配置为 `YIKE_PILOT_COLLECTION_MODE=four-platform-monitor-v1`。没有修改环境、重启或读取认证信息。
- 截至 main `3a4ae9a`，上述客户端装配文件相对 fbf9f94 无变化。
- 非作者 `platform_query_full_review` 对 fbf9f94 同一入口独立只读核对，确认没有另一条普通 Mac 原生运行路径；`NOT_REQUIRED` 不是原生运行时 READY。匿名 controller 技术存在但当前部署不许可，不能作为兜底。此独立核对没有重复测试、构包或访问生产。

## 如何继续

1. 当前 Mac 包先验证实际账号登录、正常重启会话及画像/资料等服务端流程，不让用户反复尝试不存在的原生连接能力。
2. 若继续原规划 Windows 首发，需要真实 Windows 环境完成固定同源包及平台流程；保留原完整目标。
3. 若用户需要以现在手头的 Mac 完成四平台全链路，应明确把 Mac 原生运行包/安装/权限/进程和平台实测纳入交付，再做跨平台设计。不能仅移除 platform 检查、读取开发机环境或复制登录态冒充正式支持。
4. 公开来源可以作为独立受控验证路径，但不能以 V2EX 近期几十条抽样代替小红书等渠道或证明跨行业价值；不未经验证直接切换生产模式。

这项核对暴露的是实际交付前提，不是“再跑一轮测试”能解决的问题。完整 Goal 保持 ACTIVE；没有将 Mac 原生支持默认为当前已批准或已实现。
