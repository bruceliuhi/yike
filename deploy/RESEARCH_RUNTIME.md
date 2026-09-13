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

`pilot.research_container_broker.TaskContainerBroker` 当前仅有特权侧create/status/stop核心，不是HTTP服务，也未从客户API调用。配置固定镜像内容摘要及私有tasks/ledger目录，请求仅给tenant/task/run UUID和generation；任务目录由这些字段的hash确定。create先以O_EXCL建立不含秘密的登记并fsync，再执行固定docker create；已登记的UNKNOWN或残缺登记永不自动重建，重复请求不延期。status/stop须核验登记与容器归属标签，停止后重查运行状态，不以CLI退出作为停止证明。当前没有start、输入/事件转接、后台期限扫描或崩溃恢复服务；后续必须接齐才能使用。保留created容器/登记供核对，不自动删除UNKNOWN。此核心尚未运行真实Docker操作，合成回执测试不等于Docker隔离验收。

broker必须以UID10001运行并单独获得Docker控制权限；不兼容UID启动即拒绝，不通过放宽共享目录权限解决。API仍不获得Docker socket。私有任务目录/socket和容器运行UID保持一致；Mac定向测试仅替换UID常量适配本机文件所有者，不证明Linux部署权限已经通过。升级时新create采用当前固定digest，旧任务status/stop用持久登记中的原合法digest核归属，不能因升级丢失旧任务清理能力。

### 后续源码接续：启动与独立守护（未部署）

`with broker`获取ledger独占监督锁并启动独立watch线程；`execute(identity, manifest, emit=...)`才可执行固定start -ai，输入只走stdin，stdout限制2MiB/16块队列，最多2个执行槽。持久started禁止重启/重复请求再次启动；cancelled先落盘，CLI退出后仍核对容器，未确认启动的created不冒充STOPPED。终态确认后落terminal跳过历史反复查询；活动任务先检查，每轮最多一条历史UNKNOWN轮转，每次Docker命令2秒超时。该超时是有界核对，不保证失联Docker已停止；UNKNOWN保留，不自动重试任务。

重启先取消旧started，仍未确认终态时拒绝新执行，守护继续尝试清理。监督进程存活时独立于execute输出消费检查期限；监督进程本身崩溃期间，尚需部署服务自动重启触发恢复，不能宣称已经有外部孤儿清理服务。`emit`由后续内部服务提供有界传输，不接受用户代码。上述源码已取代前文“无start”的历史状态，但仍未接服务/worker或实际Docker验收；不上传镜像或启用客户研究。

同进程execute结束但物理状态未确认STOPPED，也会保留优先回收并加入新启动门禁；不需要等broker重启才限制孤儿增长。槽位释放只代表本地attach调用结束，不代表容器已停止。

### 私有服务与无特权客户端（源码接续，未接客户任务）

`python -I -m pilot.research_broker_service --socket <私有socket路径> --image <固定sha256> --tasks-root <私有任务根> --ledger-root <私有登记根>`提供同UID/0600 Unix socket服务，绝不监听TCP。固定POST `/v1/create`、`/v1/status`、`/v1/stop`、`/v1/execute`，body最多1MiB、最多4请求线程；执行返回NDJSON块和最终物理状态，不把STOPPED当研究成功。不得通过公网反代暴露这些接口。服务主进程上下文拥有broker守护，仍需后续部署配置自动重启恢复。

客户服务使用独立 `BrokerClient`，只依赖httpx和纯身份合同，不导入Docker控制；固定socket与路径、校验task key/状态/帧/2MiB总量。真实本地UDS合成broker往返验证了小事件在任务结束前可见；原64KiB累积延迟经RED复现修复。关闭时最终准入再查halt/alive，避免status耗时期间服务停止后继续启动。当前尚未将此client注入实际mission、配置生产挂载或运行真实Docker，不能据服务接口通过声称客户研究已经隔离执行。
