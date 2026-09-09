# V02-09A ASAR校验路径兼容修复

> **For agentic workers:** REQUIRED: Use `subagent-driven-development` if the current harness supports helper agents; otherwise use `executing-plans`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复Windows下校验器对实际存在的ASAR入口误报缺失，不改打包内容或放宽检查。

**Evidence:** 干净提交f4d4a56的完整链已通过550单测/2个适用条件skip、native-smoke和Squirrel制作；archive-check失败。真实ASAR中主入口80406字节、preload502字节、index584字节均存在，`asar.extractFile` 使用 `path.normalize` 后可读取；当前库按本机分隔符遍历目录。

**Architecture:** 仅在 `desktop/scripts/verify-package.mjs` 调用ASAR读取的边界把既有可信逻辑路径转为本机路径。保留固定CJS入口断言、manifest白名单、非空字节、环境文件/私钥排除和SHA计算；不改变原产物、不修改第三方包、不删除任何检查。

**Tech Stack:** Node.js 24.15+、既有 `@electron/asar`、Vitest、PowerShell。

## Chunk 1：真实归档回归与最小修复

- [ ] 新增 `desktop/tests/verifyPackage.test.mjs`，在含空格的独立临时目录创建真实ASAR并通过实际CLI运行脚本；运行 `node node_modules/vitest/vitest.mjs run tests/verifyPackage.test.mjs`（desktop目录），完整包在当前Windows预期因入口查询失败而RED，不mock `extractFile`。
- [ ] 唯一生产修改为既有 `read` 中 `asar.extractFile(archive, path.normalize(name))`；重跑上条命令预期GREEN，原始manifest资产路径必须先经现有白名单校验，不能规范化后洗白。
- [ ] 反例覆盖缺主入口、错误main值、缺preload、缺manifest资源、空资产、非法manifest原路径（包括 `assets/../escape.js`）、包内.env/私钥拒绝；检查实际错误原因、摘要与资源数，不能因错误发生更早而误判负例通过。测试支持当前Node24.15+，不限定Mac为x64。
- [ ] 独立规格、架构/代码/质量复审；根代理复跑新增与相关构建回归及typecheck，不从作者结论直接推断通过。

## Chunk 2：版本绑定的原产物与完整链验证

- [ ] 先用修复后的CLI对现有失败链同一ASAR重新校验，前后SHA256均须为 `aee5e624987dd99f4b6b820d92003e2f00a1c5904a5aaac23b01af55a702a52a`；不改写旧失败报告。
- [ ] 由root提交后从干净新SHA运行 `./desktop/scripts/build-windows.ps1`，验证全部阶段含包内冒烟；分别保留旧失败与新报告，任何失败如实记录。真实安装/签名/缩放仍未验收。

文件边界仅校验脚本、新测试；计划及最终QA由root维护。不改Maker、runtime、依赖、UI、后端或verify-package的声明边界。
