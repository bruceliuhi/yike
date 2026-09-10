# Windows 采集进程生命周期 Implementation Plan

> For agentic workers: use subagent-driven-development and TDD. 用户已批准精简版独立推进；本批一次独立SPEC→代码/架构/质量审核，定向验证，不重复构包。

**Goal:** 修复实际 `run_supervised_process` 在Windows的取消/超时和异常退出清理，保证只停止本次受控进程树，不冒充真实采集接通。

**Architecture:** Windows专用stdlib ctypes Job Object，设置KILL_ON_JOB_CLOSE且不允许breakaway。Python隔离启动器先阻塞于私有stdin门；父进程成功assign job后才开放门，启动器shell=False运行原命令并传回退出码，命令不接收门stdin。Job句柄不继承。失败不退回无Job执行；正常结束也清理遗留后代，取消/超时/回调异常有界终止并核查Job活动进程数为零。POSIX原行为保持。

**Tech Stack:** Python3.11 stdlib/ctypes、Win32 Job API、现pytest，不新增依赖。依据[微软Job文档](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)。Base c08fd03；Win独占下列模块，不改Mac来源映射/发送回复或SQL。

启动细节：使用当前Python的绝对 `sys._base_executable` 运行隔离门，不使用Windows venv的转发器作为Job根；基础解释器不存在则关闭执行，不回退。原采集命令及其venv不变，仅在开门后运行。[Python说明](https://docs.python.org/3.11/library/venv.html)确认Windows venv使用转发器。正常父退出时先poll并保留退出码，再清理仍持有stdout/stderr的后代，不能只等communicate判完成。

## Chunk 1：真实Windows进程树

### Task 1：原生Job封装（helper）

Files: 新 `app/windows_process_job.py`、`tests/test_windows_process_job.py`。

- [ ] RED：真实子进程及孙进程在开门前不得执行；开门后正常输出/返回码；terminate清理树，close安全幂等；父端异常退出由OS清理。使用测试专属PID/句柄和finally清理，不按进程名称批量终止。
- [ ] 提供 `WindowsProcessJob`：create非继承job，assign(Popen)、terminate_and_wait(timeout_seconds)、close；以及 `launch_job_process(command, cwd, env)` 返回(process,job)，打开门前完成assign。Popen保持stdout/stderr PIPE,text=True，关闭并置空gate stdin后可反复communicate(timeout)。无需命令stdin、shell或全局环境更改，固定CREATE_NO_WINDOW；错误脱敏。
- [ ] ctypes完整argtypes/restype和正确结构布局；Set/Assign/Terminate/Query/Close失败不伪报成功，启动失败清理job与唯一启动器并reap。只在Windows调用，非Windows安全import。

### Task 2：现supervisor接入与定向验证（root）

Files: 修改 `app/collector.py` 仅 `run_supervised_process` 的Windows分支；新增 `tests/test_windows_collector_process.py`。

- [ ] 先实际RED复现取消/超时因os.killpg缺失；测试命令只用本机Python输出/等待/创建测试后代，不启动平台。
- [ ] Windows走launch_job_process，取消/超时/回调异常/正常结束均确认Job树清理，保持原结果标记与回调接口；POSIX分支不变。原父码在正常清理前保留，不因清理残留子进程改写成功码。
- [ ] 实机覆盖正常stdout/stderr/非零码、取消、超时、回调异常、正常父退出遗留后代、启动失败。root运行Python3.11 `-m pytest -q tests/test_windows_process_job.py tests/test_windows_collector_process.py`；相关旧纯测试按影响选择，不跑已知POSIX专属测试冒充Windows。
- [ ] 非作者一次整批冻结树审核；正常main提交/推送，任务书引用简短事实。后续运行时私有目录/路径、worker和批次恢复仍未完成，本片不构包、不关闭Goal。
