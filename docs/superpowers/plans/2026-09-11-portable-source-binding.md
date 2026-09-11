# Windows 候选源码绑定修复

基线6d50331。执行既有交付要求“新payload和Electron必须来自同一产品基线”，用systematic-debugging/TDD修复，不改变产品范围。

根因：Forge/Vite共用portableBuildInput只验清单摘要及payload自报clean，不核验manifest.source.project_commit与当前Electron源码。旧payload可以通过新客户端构包，当前交接仅要求人工检查。

本批：

- [ ] 定向RED：真实临时Git仓库中，同SHA且干净允许；缺失/错误payload SHA、当前tracked/untracked改动、无Git来源均拒绝；非Windows保持不要求payload。只调用构包输入函数，不make。
- [ ] desktop/build/portableBuild.ts在Windows输入路径中读取固定项目根Git HEAD/状态，与payload SHA精确相等且都干净才通过。固定根从该build模块位置解析，不采用环境自报SHA；测试可传明确临时根。Git命令不经shell、有timeout/输出上限、错误脱敏；不继承GIT_DIR等重定向仓库变量。复用Forge/Vite现调用，不改包格式/运行时凭据/安装器。
- [ ] 新增/旧受影响portableBuild.test.ts定向及typecheck一次；一份独立整批审核。无Windows运行环境不能冒充已构包/安装/平台验证。
- [ ] 更新WIN_V02_CURRENT_CANDIDATE固定源版本与这项门禁；更新唯一证据及状态入口，正常push main。后续纯文档提交不改变固定候选，不反复make。完整V02仍未完成。

## 实施与验证

源码 `c8344082b3e483b7c8d86b54017725d0c95ad2a4`：上述实现及交接更新完成，推送状态以远端核验为准。Windows旧候选23d1793保留历史，当前新增画像/策略/模型功能需要同源新payload，不追认旧包。

- RED：9项中6失败、3通过，复现错误SHA、脏工作树、无Git来源被旧实现接受；修复后同组9通过（1.03秒），TypeScript与diff检查通过。未跑全量、未make。
- 独立非作者整批审核GO，绑定base `6d50331` → source `c834408`，无阻断发现；静态核对Forge/jiti和Vite加载器保留原模块路径，未重复测试。审核记录在本工作树私有Git ledger的 `sdd/portable-source-binding-final-review.md`，不将机器私有路径作为其他AI的执行依赖。
- 固定候选更新为上述源码SHA；后续纯文档提交不要求重构包。尚无本次Win ACK、payload、Setup、安装/平台/生产/UAT证据；完整V0.2未完成。
