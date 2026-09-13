# 独立研究运行镜像（未接生产任务）

## 长期管理服务部署接续（2026-09-13，尚未启动）

用户在明确说明长期Docker控制权限、隔离/回收验收后启用生产、不改其他项目、不外联和不增加模型预算的请求后回复“推进”。本次依此准备独立 `compose.research-broker.yml`，不把此前一次性探针授权复用为长期授权。使用单独Compose项目 `yike-research-broker`，无端口/网络/供应商环境文件，UID10001仅管理服务附加经实查的Docker组；该权限仍等同宿主控制能力，不因非root宣称低权限。

启动前：绑定包含最新生命周期修复的不可变研究镜像；检查宿主Docker CLI兼容性和socket组；确认 `/var/lib/yike-r` 没有其他项目占用，再建立control/tasks/ledger三个UID10001私有0700目录。Compose禁止自动建立宿主目录。tasks宿主与容器路径相同，否则Docker daemon无法找到任务挂载；客户API后续只挂control和tasks目录，不挂ledger或Docker socket。新配置不自动改变客户服务或启用研究环境变量。

放行顺序：独立审核配置→固定版本镜像→管理服务启动→真实有界任务的退出码/时间/物理终态→管理服务异常退出后的自动恢复及旧任务不重启→客户研究接线与一次已批准预算内真实任务。未取得这些证据不得启用客户能力。配置静态测试不替代上述门禁。

本批独立初审发现P1：持久control socket在异常退出后残留，阻止自动重启。修复只在取得ledger独占锁后，对同UID私有父目录中的socket做有界连接探测；仅ECONNREFUSED且inode未变才删除，活连接/文件/链接/未知错误拒绝。新增真实测试子进程kill后恢复HTTP监听及拒绝替换用例；配置与服务两文件9通过/1.88秒，差量独立复跑PASS。仅证明本机socket恢复，不替代Linux管理服务重启及旧任务回收。

回退顺序：先停新研究准入，确认活动任务物理停止；UNKNOWN时保留管理服务继续核对，禁止直接删除登记或任务目录。确认无活动任务后才能停止独立Compose项目；保留ledger和证据，客户服务恢复先前镜像/配置。不得使用down -v、全局prune或清理其他项目容器。尚未切换客户配置时无需重启客户服务。

一次性broker真实验证更新：用户明确授权后，专用临时broker容器获得Docker socket，客户API与研究任务容器未获该挂载；复用68959061…候选执行真实create/execute/status，返回STOPPED/runtime_failed，重复create没有重启。测试及临时资源已结束清理，未安装长期broker或切换生产。未记录容器退出码，故本次不证明短期限正确触发或正常研究成功；后续回收验收须在清理前记录实际退出码、终态和时序。权限仅涵盖该一次性验证，不自动延伸为长期宿主控制授权。

服务器加载状态更新：`yike-research:0.153.4-0b80fe9` 已通过 save/load 载入授权服务器，`docker image inspect .Id` 为 `sha256:68959061b1538e1a7e9963aba94cb9e55710b1d0e3b691cdc603e3eb199c2d13`，revision标签对应0b80fe9。broker使用服务器本地实际可解析的不可变内容ID；本机manifest-list摘要d62253…不是该服务器的本地image ID。实际同UID10001两容器、无网络/只读根、客户端只读挂载任务目录下，TaskSocketRelay至网关UDS固定HTTP探针通过，临时容器和目录清理完成。该结果仅证明Linux跨容器UDS传输可行，不证明许可网关/模型/PG/研究任务或broker崩溃回收通过。生产app未切换且复查healthy；下文“未上传服务器”为历史阶段记录。

最新本机构包（源码 `0b80fe9`）：服务 `yike-ai2026:0b80fe9-trial` / `sha256:071d4d66f3e75f83d4df76c62b96ef89e59f243ce3348abf642ecfb67621526d`；研究 `yike-research:0.153.4-0b80fe9` / `sha256:d62253eaf72d1fb5dccb31d4b6f4513ba8c718e63de909d371ea49c2a14dec7f`。两者均已实际构建，研究镜像包括下文新增relay/入口与接线模块。实际Linux容器无网络/只读/UID10001检查通过服务导入、Codex版本、MCP导入、固定入口拒绝非法manifest；未调用模型，MCP导入不等于本版本协议端到端通过。尚未上传服务器，不能替代跨容器socket、真实broker生命周期和客户任务验收。下文40b2f65镜像证据仅作历史记录，不追认为本版本证据。

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

### mission适配源码接续（尚未配置启用）

`BrokerMissionExecution`接入现有`run_public_research_mission(..., broker_execution=...)`，只允许有宿主动作许可及编译上下文的研究分支；宿主不需Codex/Python可执行文件，不回退本地进程。任务目录按身份hash唯一创建；模型/搜索key不进manifest。原事件解析和citation展开仍由宿主完成，合成broker输出不是可信采购事实或新的真实研究证据。取消/格式错误先撤销宿主后续动作许可，再请求物理停止，停止未确认写broker_stop_unknown；短令牌虽仍在临时网关内，revoked围栏拒绝后续effect。

broker空闲执行每秒发协议心跳，client流读超时12秒、host reader回收上限13秒，公共合同绑定以覆盖2秒CLI等待+三次2秒Docker核对及线程回收；host适配器有界队列消费，按原deadline/cancel回收。最终STOPPED帧且完整流已确认时不重复stop查询。当前尚未接动态配置factory与生产挂载，前文“尚未注入mission”由本节源码状态替代；真实容器/模型/客户路径仍未验收。

### 动态配置与任务身份接线（源码已接，未部署启用）

启用隔离分支须同时设置 `YIKE_PILOT_RESEARCH_AGENT_BROKER_SOCKET` 和 `YIKE_PILOT_RESEARCH_AGENT_TASKS_ROOT`，仍要求原有 API_KEY/MODEL/SEARCH_API_KEY；不得同时设置宿主 CODEX_BINARY/PYTHON_BINARY。固定容器执行路径不在宿主检查。缺字段、相对路径或混合配置直接拒绝；运行时装配检查私有 socket，配置故障不回退宿主执行。未配置 broker 的既有路径保持兼容，不代表生产已经启用隔离。

例如 control socket 使用 `/run/yike/control/broker.sock`、tasks root 使用 `/run/yike/tasks`；任务根长度不超过23字节，以容纳hash与UDS路径。生产应挂载私有 control 目录而非单独 socket 文件，避免服务重启换 inode 后继续使用旧挂载；API 不挂 Docker socket或broker登记目录。这些是部署要求，尚无实际挂载验收。

动态 runtime 在数据库选举同一事务保存确认的 tenant_id，再绑定 task_id/run_id/generation 创建 BrokerMissionExecution；不在执行途中改用另一个当前租户。mission 返回 broker_stop_unknown 或 broker_stream_unknown 时，先保存原 stop_code，再结束本轮协调器，不能被用户取消覆盖为 CANCELED。协调器 STOPPED 是停止推进，不是容器物理停止证明；后者仍由 broker 核对。32项定向检查通过，未使用真实PG/Docker或调用模型。
