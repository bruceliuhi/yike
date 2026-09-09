# Mac 原生文件与叠层确认验收

本轮基线为 e65e3fe36692cd4b0100434b90751556e46bb0ec，独立构包来自 Git archive，排除未提交的四个 raw candidate 草稿。基线 [包清单](baseline-e65e3fe/final-mac-package.json) 与 [输入](baseline-e65e3fe/final-build-inputs.json) 保留，不与后续修复包混用。

## 实际发现与修复范围

基线包的 P04 文件导入已通过：原生选择器取消后表单为空；导入专用 TEST 文件后名称自动填写，原文 76 字；选择空白文本被拒绝且保留先前原文；保存后生成单条“本机草稿”，明确未同步。分别见 01–06 的 AX 记录与 [导入截图](screenshots/imported-text.jpg)。

取消已修改的资料时发现缺陷：[截图](screenshots/discard-before-fix.jpg)中“放弃未保存的资料？”可见，但 [AX 记录](07-edit-discard-guard.txt)仅暴露底层抽屉。共享 Modal 同时声明多层 aria-modal=true，初始焦点停在容器；这两个因素作为修复方向，不能仅由截图断言具体浏览器内部根因。第一步只同步活动层的模态声明，未改变设计布局、业务流程或数据权限。回归测试先失败再修复，见 [RED](logs/modal-red.log) 与 [四文件定向 GREEN](logs/modal-green.log)。

## 证据边界

- fixtures 仅为本轮创建的 TEST 本地资料，未读取真实客户文件，未上传或对外发送。
- “保存草稿”是本机会话草稿，不是 macOS 保存文件对话框，也不是客户服务持久化。
- 真实客户 CSV 导出、备份保存的原生对话框需要对应认证数据路径，本轮未虚构该条件；这些仍单独待验。
- Windows 安装、缩放及实机流程由用户执行，本轮 Mac 结果不替代。
- 基线包独立复核见 [报告](reviews/package-review.md)，报告中的相对清单名现位于 baseline-e65e3fe/。

修复包与原生复验见下文；不宣称整体上线或 Goal 完成。

## 中间候选 9d1825b 未关闭原生缺陷

[中间包清单](intermediate-9d1825b/final-mac-package.json)保留。只修 aria-modal 后，09 AX 仍停留底层；按一次 Tab 才得到 [10 顶层按钮](10-after-tab-accessible.txt)，因此不追认为修复通过。9b137fc 进一步将初始焦点放到最上层首个可操作控件（当前为关闭按钮），无控件时退回容器；聚焦不执行确认或关闭。原焦点陷阱、Escape、逐层恢复继续复用。

正常合入 d6d9ff5 后最终源码候选 f20b404240bfe87733bee62ffb4b9142d18d8567。此包包含来件候选原文读取与显式请求恢复基础，不等同全部候选操作已接到界面。类型与构包通过；最终 [86文件、1309项 UI及候选相关回归](logs/final-ui-integration.log)通过，不与先前985或历史全量结果累加。

## 最终包原生复验通过的范围

[最终包清单](final-mac-package.json)绑定 f20b404；354 tracked 输入均与提交一致，ASAR `04c0645e7e1ada385212c789343054b97587286289305d1671d759b51565fae2`，ZIP `f5b15bf9d1f04f4472f98ce6c61ad77867d5de6767a37eb1a25f9f4bdbb0a9b7`。严格 packaged smoke、生产 TEST 排除与 ZIP 内 ASAR 相符。可运行产物位于 `desktop/out/native-files-f20b404/`；大体积二进制未纳入 Git。

1. 从确切 app 路径启动，经业务画像→资料与案例→添加资料→原生打开选择本轮文件；[11](11-final-import.txt)显示自动命名和76字。
2. 点击取消，未发送 Tab 或其他辅助操作，[12](12-final-guard.txt)直接暴露最上层确认的关闭、取消、放弃修改按钮，初始焦点在关闭按钮。
3. 点击确认框取消，[13](13-cancel-keeps-import.txt)保留原导入；再保存，[14](14-final-saved.txt)显示单条本机草稿与未同步提示。
4. 重新编辑名称后取消，[15](15-edit-guard-accessible.txt)重现原缺陷场景且顶层立即可达。实际点击放弃修改，[16](16-edit-discarded.txt)返回原资料；[17](17-original-restored.txt)重开核对名称、正文及内部引用范围未变。
5. [修复前](screenshots/discard-before-fix.jpg)与[最终同场景](screenshots/edit-guard-final.jpg)同时并排审阅：相同1080×768截图尺寸，标题、抽屉、确认框、按钮位置及文字无布局变化；时间与指针位置变化不作缺陷。截图尺寸不冒充CSS视口/Windows缩放验收。
6. 已重新打开同一路径客户端供查看，记录在 [运行绑定](final-native-process.json)。本轮最后退出没有完整记录原生关闭确认全过程，因此不新增宣称关闭防丢失门禁通过；此前生命周期证据仍绑定各自旧包。

首次 CUA 粘贴 Go to Folder 路径超时，实际输入未生效；读取路径栏后用原生 setValue 定位成功，没有重复导入或将工具超时归作产品缺陷。

独立[代码审核](reviews/modal-code-review.md)、[架构审核](reviews/modal-architecture-review.md)与[来件集成审核](reviews/incoming-integration.md)保留各次候选范围。Windows、客户服务原生导出/备份和其余完整Goal验收仍分别继续。
