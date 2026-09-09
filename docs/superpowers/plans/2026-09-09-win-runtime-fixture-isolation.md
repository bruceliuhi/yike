# V02-09A 运行时测试夹具文件隔离 Implementation Plan

> **For agentic workers:** REQUIRED: Use `subagent-driven-development` if the current harness supports helper agents; otherwise use `executing-plans`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除运行时测试夹具与正在执行的原Node共享硬链接文件对象的问题，保留真实CLI、子进程、失败阶段及严格清理断言。

**Architecture:** 仅修改 `desktop/tests/windowsBuildRuntime.test.mjs` 的夹具构造与对应回归。每个临时Node用独立copy，不使用hardlink、symlink或修改源Node；测试仍启动实际二进制，不mock生产执行。旧失败目录保留，不扩大权限、加无限重试或忽略清理失败。

**Tech Stack:** Node.js 24.15+、Vitest、Node fs/child_process，沿用现有架构适用条件。

**Evidence:** root在19:44:29合跑得到1 failed/84 passed/2 skipped，失败位于临时目录清理的EPERM（exec chunk 3c807d）。只读检查AvlVDu残留Node与bundled源Node的NTFS File ID均为`0x00000000000000000005000000273259`；夹具当前优先linkSync。没有故障时句柄证据，不认定杀毒软件或特定进程为原因。后续3c16fac完整链568/2通过属于另一轮，不擦除这次失败，也不证明间歇清理已修复。

## Chunk 1：独立文件对象与真实并发存活

**Files:** Modify/Test: `desktop/tests/windowsBuildRuntime.test.mjs`。不改生产runtime/evidence、依赖、已有ASAR或安装包。root负责本计划及QA文档。

- [ ] 新增真实夹具隔离测试：源Node、A、B的`statSync({bigint:true})`文件身份(dev/ino)不同，A/B不是symlink、hardlink（nlink=1），摘要与源相同。先运行 `node node_modules/vitest/vitest.mjs run tests/windowsBuildRuntime.test.mjs -t 'independent'`（desktop目录），原优先link实现在本机应因同一文件身份明确RED；不通过写入来探测别名。
- [ ] 把夹具构造改为`copyFileSync(process.execPath, node)`，删除linkSync导入；不修改执行命令、状态或断言。重跑前项应GREEN。
- [ ] 有界真实进程验证：A启动一个可通过IPC应答的Node子进程（windowsHide），等ready后清理本次新建B的精确私有根，确认A仍回应并且源Node摘要不变；随后正常关闭A并等待close，在finally中限时终止仅该测试子进程。不要操作AvlVDu/Mk7kCl或其它历史目录；遵循现有路径验证，不能在A进程尚未退出时清理A。
- [ ] 不把结构性隔离RED称为EPERM的确定性复现；即使原hardlink的存活测试偶尔通过也保留身份反例。不得以增大超时、跳过Windows或捕获并忽略清理异常作为修复。
- [ ] 作者运行该文件及相关evidence/ASAR/renderer/staging回归，独立reviewer复核规格、架构/代码/质量并实跑。根代理复跑，记录每一轮而非挑选成功结果；检查新增夹具/子进程无遗留，类型和diff检查通过后提交。

## Chunk 2：主线与证据

- [ ] 从干净修复SHA执行完整Windows构建链，旧失败报告与3c16成功报告分别保留，新的通过仅代表该次自动链，不代表所有环境长期无间歇问题。
- [ ] 更新唯一任务书和Win QA，保留17 high、真实安装/签名/平台能力未验收；独立文档复审后正常fetch/integrate/push main，不关闭共同Goal。
