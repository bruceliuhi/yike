# 新包 macOS 可见验收

2026-09-10，构包源码 f18a922。测试专用后续提交不改变产品字节；完整绑定见 [构包记录](release-mac-package.json)和[实际进程](native-launch-binding.json)。

- 实际启动本次 `out/意客AI-darwin-arm64/意客AI.app` 内的二进制，PID 15583，ASAR SHA-256 `79a52de9d645378e0903fd93c4f49ac4c9ce703592fc1b537875708b372c86fa`。
- 使用独立 `/tmp/yike-native-state-20260910-release` 用户目录，并移除服务地址环境变量。没有开发服务器、测试服务或真实客户会话。
- [冷启动截图](native-cold-start.png)及 [AX](native-cold-start.txt)显示真实 `yike://app/index.html` 工作台、平台原 Logo、待连接状态和公开研究样例；没有白屏。
- 实际点击“创建获客任务”后，等待页面完成加载。[任务页 AX](native-task-status.txt)中五个平台复选框的可访问名称与可见文本均为“读取失败”，修复的状态一致性已核对。“本次最多使用搜贝”输入与未连接服务说明同时存在。

随后准备输入任务草稿时，CUA 返回“Mac is locked and automatic unlock could not unlock it”。没有绕过锁屏，也没有继续声称输入、退出取消或重启链已经完成。此前一次使用旧 AX 编号未输入到任务名称，第二个编号报无效；未把该工具操作当作输入成功。新包退出/重启、原生文件选择器及 Windows 验收仍待后续实际执行，旧版本相应证据只保留其原适用版本。

本记录只证明新包冷启动及上述可见状态，不证明真实平台连接、计量扣费、数据采集或对外收发。构包内真实 IPC/renderer 与隔离服务桥冒烟分别见 [严格 smoke](release-packaged-smoke.log)、[服务桥 smoke](release-native-service-smoke.log)。
