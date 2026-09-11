# Windows 候选源码绑定修复

基线6d50331。执行既有交付要求“新payload和Electron必须来自同一产品基线”，用systematic-debugging/TDD修复，不改变产品范围。

根因：Forge/Vite共用portableBuildInput只验清单摘要及payload自报clean，不核验manifest.source.project_commit与当前Electron源码。旧payload可以通过新客户端构包，当前交接仅要求人工检查。

本批：

- [ ] 定向RED：真实临时Git仓库中，同SHA且干净允许；缺失/错误payload SHA、当前tracked/untracked改动、无Git来源均拒绝；非Windows保持不要求payload。只调用构包输入函数，不make。
- [ ] desktop/build/portableBuild.ts在Windows输入路径中读取固定项目根Git HEAD/状态，与payload SHA精确相等且都干净才通过。固定根从该build模块位置解析，不采用环境自报SHA；测试可传明确临时根。Git命令不经shell、有timeout/输出上限、错误脱敏；不继承GIT_DIR等重定向仓库变量。复用Forge/Vite现调用，不改包格式/运行时凭据/安装器。
- [ ] 新增/旧受影响portableBuild.test.ts定向及typecheck一次；一份独立整批审核。无Windows运行环境不能冒充已构包/安装/平台验证。
- [ ] 更新WIN_V02_CURRENT_CANDIDATE固定源版本与这项门禁；更新唯一证据及状态入口，正常push main。后续纯文档提交不改变固定候选，不反复make。完整V02仍未完成。

## 实施与验证

执行中。Windows旧候选23d1793保留历史，当前新增画像/策略/模型功能需要同源新payload，不追认旧包。
