# 最终修复包实际原生操作

2026-09-10 01:25–01:28，Mac arm64，源码 `8ddafab6cc4cea21c244dcf1f052bf04defe8e87`。直接运行实际 .app，不用开发服务器、不替换 dialog、未配置客户服务。

- ASAR：`aec0b946be4ca147e940e3c4ec1f3c0652104585be843ff69ebf95f2869da50d`。
- 独立 user-data-dir `/tmp/yike-native-final-20260910`，初次 PID 1244。
- 冷启动可见工作台、机会简报及公开研究样例，无页面错误（native-workbench.png）。
- 点击“创建获客任务”，输入“最终包验收”和 50 搜贝，保存为本机会话草稿；没有实际启动任务或消耗搜贝。
- 返回线索采集后 Cmd+Q，出现原生“继续编辑／放弃更改并关闭”警告（native-quit-warning.png）。继续编辑后从列表恢复草稿，名称和 50 搜贝保留（native-continue-preserves-draft.png/.txt）。
- 再 Cmd+Q，明确放弃关闭，命令进程正常退出码 0（exec 4363c0）。
- 同包同 user-data-dir 重启，实际进入工作台（native-restart-workbench.txt），再进入线索采集显示“本机草稿 0”，无验收任务（native-restart.png/.txt）。

native-workbench.txt、native-saved-draft.txt、native-quit-warning.txt 为同状态复取的简短 AX 输出，不作为完整页面树；截图、恢复值 AX 差量及重启完整 AX 相互补充。日志只有 Node deprecation 与 macOS 输入法消息，没有前一版 CSP/React renderer error；严格 smoke 独立捕获并检查 error 级别。

这里只验收无客户服务情况下的真实客户端、输入和会话退出，不代表正式研究、平台登录、原生文件保存选择器、Windows 生命周期或签名发行。中间 befacea 包的监控流程记录保留在 react-only/，不充作本最终包证据。
