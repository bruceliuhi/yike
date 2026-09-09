# 合并 4eca413 的原生增量验证

启动实际 Mac arm64 `.app`（ASAR d7f2d2c0cc4b0cfa3f3034b0074287a66ef00097d827d8f599e52c6f578006af），使用独立空目录 `/tmp/yike-native-merged-20260910`，未配置客户服务。进程与打开的可执行文件/ASAR 见 [native-process.json](native-process.json)。

通过 CUA 操作可见原生窗口，完成：

1. 冷启动进入工作台，无页面错误恢复屏；[截图](native-workbench.png)及[完整 AX](native-workbench.txt)。
2. 点击“创建获客任务”，懒加载后显示名称、画像、可编辑搜索条件、平台范围、运行设置与搜贝上限；[截图](native-task-form.png)及[完整 AX](native-task-form.txt)。本次只读访问，没有创建或执行任务。
3. 由侧栏进入“账号与授权”，显示各平台连接/能力及服务未配置提示；[截图](native-connections.png)及[完整 AX](native-connections.txt)。未显示已授权假成功，没有进行平台登录或触达。

此项仅覆盖本合并包的可见冷启动与路由加载。草稿/退出/重启完整链属于上一修复包 aec0，详见 ../fix/native-lifecycle.md；不得挪作本合并包完整生命周期证据。当前截图也不代替与 R3/R4 同视口逐项视觉对照。

仍观察到任务平台复选框 AX 名称“读取中”与可见“读取失败”不一致，已登记为后续状态文案修正项。真实服务、原生文件选择器、Windows 实机和签名仍待验收。

归档文本仅去除行尾空白及末尾多余空行，不改变内容或结果。
