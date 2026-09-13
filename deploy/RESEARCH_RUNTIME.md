# 独立研究运行镜像（未接生产任务）

该镜像供后续每任务隔离执行器使用，不能替换共享客户API服务镜像。镜像构建不启用动态capability，不装账号，不配置供应商密钥或数据库。

## 固定输入

- 基础为已验收的普通服务镜像，构建时显式提供不可变镜像引用；不得用latest。
- 当前Linux amd64，Python3.12；Codex完整官方包0.153.4，Docker ADD强制SHA256核验。
- `uv sync --frozen --no-dev --no-install-project --extra research`复用项目锁，MCP为1.28.0。
- `.pth`让隔离模式Python `-I`加载镜像内`/app/pilot`，不依赖宿主目录或PYTHONPATH。
- 默认入口只输出Codex版本，非root；启动业务任务仍缺broker接线。

```sh
docker build --platform linux/amd64 -f deploy/Dockerfile.research \
  --build-arg SERVICE_IMAGE=yike-ai2026:40b2f65-trial@sha256:07640dea5cebfc8eba2af2b4fecb266a5c31d024bc0b0808e1dc0db8667cce74 \
  -t yike-research:0.153.4-40b2f65 .
```

上述引用是2026-09-13本机候选，不表示已上传服务器registry。更换基础镜像后重新绑定版本并验证，不把本次证据追认为新镜像证据。SERVICE_IMAGE无默认值是有意的，必须明确传入。

## 已取得与未取得证据

本机实际构建摘要：`sha256:bc280315a7423b5c031dfbba29ed8eaadea4d18cda35dac8b380a9ac167beef5`。在无网络、只读根、cap-drop ALL、no-new-privileges、UID10001、512MiB/PID64限制下，Codex版本输出和真实MCP初始化/工具列表通过。没有模型调用、网页读取、PG接线或客户任务。

正式执行必须由受限broker绑定task/run/generation，固定镜像digest、命令及挂载，独立截止时间、取消和未知结果核对。客户API不能拥有Docker socket；容器只能访问自己的任务socket，不能挂共享HOME/源码/账号。供应商key和DB留在宿主许可网关，容器只拿短期任务token；专属state/tmpfs解决只读HOME别名警告，不开放宿主写权限。完整CLI→MCP→宿主许可/原文账本往返、跨租户隔离及停止回收尚待实现验收。

源码现有 `pilot.research_socket_relay.TaskSocketRelay`：在容器回环临时端口将原始流量转交唯一指定的Unix socket，HTTP路径与短期token仍由宿主ResponsesBridge验证。最多4连接、每方向2MiB+64KiB、期限最多30分钟，到期或退出关闭连接，不删除挂载socket。仅有本地合成验证，未打入上述镜像、未接任务启动器；不能凭此宣称容器任务已经可用。

固定任务入口源码为 `python -I -m pilot.research_container_entry`，由后续broker固定选用，不接受客户指定命令。stdin一次性JSON仅包含version=1、model、短期token、mission、编译instructions、entry_urls、max_reads/max_requests/max_searches/max_seconds、绝对expires_at；未知字段拒绝，输入最多1MiB。网关固定 `/run/yike/bridge.sock`，Codex固定 `/opt/codex/bin/codex`，MCP解释器固定 `/app/.venv/bin/python`。普通Codex JSON事件直接交回宿主现有事件与证据解析，不在容器重建账本；返回124表示超时、130表示取消、2表示入口失败，其他为Codex退出码。临时HOME/state/work只在容器/tmp，不挂宿主HOME。broker仍须为stdin准备、整个容器及API崩溃提供独立截止回收，入口进程的finally不是替代。此入口尚未打入前述镜像或接worker，不是实际客户任务验收。
