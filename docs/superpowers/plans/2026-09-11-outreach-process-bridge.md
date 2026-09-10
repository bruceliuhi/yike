# 07B 受监督评论进程桥

基线 `abbd962`；继续已批准 V0.2，不扩大平台动作范围。使用 subagent-driven-development 执行，按用户要求整批一次独立审核，只测改变的边界。

## Global Constraints

- 固定 XHS 主帖评论；主进程提供已解析的隔离 profile，不接受 renderer 的路径或任意命令。
- 同一存活 worker/page 先 CHECK；只有现有 consumer 持久消费许可后才 EXECUTE 一次。原 context/operation 必须绑定，取消/EOF/异常不重试。
- 复用现有 Windows runtime 校验、profile 独占、私有目录和 Job 进程树监督，不修改既有启动前 assignment gate。
- 正文与控制帧只在内存传输，不写文件/argv/日志。host 与 worker 使用一次性随机鉴权的本机 loopback JSON 通道；无 pickle、无远端监听、无新增外部服务。
- 先保存 worker 取得的回执，再做 runtime 清理；清理失败不抹掉已发生事实，也不得释放同一次请求重发。未取得明确回执为 UNKNOWN。
- 这批不注册公共发送 IPC，不实际发送、不部署；Windows 实机与真实平台发送仍单列未验。

## Task 1: Python host / worker

新增 `app/windows_platform_outreach.py` 和 `app/platform_outreach_worker.py`，定向测试 `tests/test_windows_platform_outreach.py`。复用 `windows_platform_login` 的严格 JSON/路径/marker、受监督 runtime 启动方式；不要复制完整框架。host stdin 两帧，固定 schema `windows-platform-outreach-v1`：

1. `{schema_version, action:"CHECK", runtime_path, profile_path, output_path, context, timeout_seconds}`，超时整数 1–90 秒；三个目录必须隔离，profile 已存在且私有，不能给外联自动建一个空 profile。
2. READY 后可接 `{schema_version, action:"EXECUTE", operation:{requestId,claimId,dispatchBefore}}`；仅一帧，提前/重复/多余输入/EOF 取消。正文仅第一帧携带。

stdout 最多两帧，总量 32 KiB：`{schema_version,state:"READY",observation}`；`{schema_version,state:"RESULT",outcome,cleanupConfirmed:boolean}`。固定错误统一 `{schema_version,state:"FAILED",error_code:"OUTREACH_HOST_FAILED"}`，不泄露异常。外部输入单帧最多128 KiB，严格字段/重复键/NaN 拒绝。

host 建立 127.0.0.1 随机端口、32字节随机 token 经最小子进程 env 传入；worker 首帧 `{token}` 鉴权，错误连接失败关闭。host 仅接受一次连接，非阻塞 poll 做有界 framing/发送；supervisor 继续负责总超时/取消/物理进程树清理。正文不进 env。worker 从通道取 context，调用 `open_xhs_comment_channel`，发送 READY，再等待原 operation 调用 execute。EOF 立即设置取消信号；结果在 runtime exit 前传给 host。host 在 Job 清理后输出最终结果；可信结果即使清理失败仍返回但 cleanupConfirmed=false。

少量关键测试覆盖严格输入、提前/重复执行拒绝、真实 loopback framing、同页 CHECK/EXECUTE、取消、回执先于清理失败保留；固定 fake 页面/runtime 不是实机成功。允许在同文件实现小型私有 framing helper，避免新通用 RPC 框架。若实际复用存在安全冲突先报告。

## Task 2: TS NativeOutreachChannel

新增 `desktop/src/main/platformOutreachDriver.ts` 接现有 `NativeOutreachChannel`，构造参数复用 login driver 路径/固定 spawn；另传由可信 main 决定的 profileId。不修改 Win main/bootstrap/UI。

check 启动固定 Python module、发送第一帧并保留同一进程；execute 只接受相同 context，发送一次 operation 并等 RESULT。固定错误、输出限额、超时、AbortSignal/EOF 关闭、物理终止等待沿用现有 login driver 的原则。重复/并发调用失败关闭，晚回执保留；不得将未知结果当失败未投递。测试只跑新增 driver 文件和一次类型检查。

## 本批证据

TS：`tests/platformOutreachDriver.test.ts` 定向 5 passed；同批 `tsc --noEmit -p desktop/tsconfig.json` 通过。初始缺模块导致5项失败；实现后测试通过，首次类型检查发现测试 spy 的空 tuple 推断，改成显式 unknown[] 后通过。未跑全量测试、构包或外部发送。

`createPlatformOutreachDriver({...loginDriverPaths,profileId,connection})` 每次派发构造一个实例；connection/profileId 须由可信 main 同一身份的已确认连接记录解析，不能从 renderer 取路径。`check/execute` 接现有 consumer；`cleanupConfirmed()` 单独表示 host 树清理，false 不抹掉明确回执，main 应停住对应 profile 的后续动作并提示处理。`stop()` 关闭 stdin 并等待退出，不能用 Promise 取消代替物理停止。Win main/IPC 尚未装配。

Python初稿 `86ca208` 的6项解析用例不足以证明桥接。独立审核结论 **NO-GO**：READY缺真实绑定、等待stdin阻塞监督循环、EXECUTE后EOF不传播、正常退出未排空回执、接收缓冲未限额、未拒绝提前/重复操作。原6项通过不升级为通道成功；修复及真实本机socket（合成页面）定向证据集中见[host报告](2026-09-11-outreach-process-host-report.md)，仅修复差量复审，不重跑旧模块。

最终独立差量复审 **GO（代码候选）**，绑定 `333eb8ce300c9e85effc11825800f0aa9c735d18`，此前撤回GO和新增取消路径P1均保留在host报告。最终Python定向33项通过，TS定向6项通过；复审未重复测试/构包。Windows Job/ACL、实际平台发送仍未验；当前main/公共IPC/UI尚未装配，父卡和完整Goal继续IN_PROGRESS。

联核补充：TS 停止后再次 CHECK 原先仍会启动子进程，新增单例用例已复现；入口加 stopping/settled 拒绝，针对同一 driver 文件复验6项通过。类型检查复用前次，新增断言不改类型接口。
