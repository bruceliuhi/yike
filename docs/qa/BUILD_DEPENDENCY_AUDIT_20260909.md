# 桌面构建依赖核查

日期：2026-09-09。核查基准：`30da93e5ba39c9bc11227640b06094c7afe980b2`。独立审查：本机 `desktop_dependency_audit`，不是 CodexWin 或 Windows 验收。

## 结论

`REQUEST_CHANGES / BUILD_SUPPLY_CHAIN_GATE`：完整依赖树的 17 项 high 未解决，不能据此放行正式发行；本轮没有批准风险豁免，也未修改或强制降级依赖。

- Node 24.19.0 / npm 11.17：`npm audit --json` 为 17 high、0 critical；`npm audit --omit=dev --json` 为 0。主代理另行复跑后者同样为 0。
- 身份工作分支的 `desktop/package.json` 与 `package-lock.json` 和上述 main 完全相同；不是此次身份/时钟整合引入。历史 `docs/qa/ui-r3/dependency-audit.json` 已记录同一告警。
- 17 是依赖传播后的计数，不是 17 个相互独立的根因。根因是 `extract-zip@2.0.1` 的两项符号链接路径穿越/任意文件写入公告，经 `@electron/packager@18.4.4` 传播到 Electron Forge 7.11.2 构建依赖。
- 风险发生在构建机解压 Electron 分发归档时；production 依赖集未报漏洞，不代表整个构建供应链安全。

公告：[GHSA-jmr9-qjv8-65gv](https://github.com/advisories/GHSA-jmr9-qjv8-65gv)、[GHSA-7pqw-9j4j-h8q3](https://github.com/advisories/GHSA-7pqw-9j4j-h8q3)。

## 处理路径与证据边界

本次独立检查 npm 官方 Registry 时，extract-zip 最新仍为 2.0.1，没有已发布安全版本；Forge 最新仍为 7.11.2，Packager 最新线仍依赖受影响包。这是带日期的检查，不保证未来不变化。

V02-09 发行前需重新核对上游：有修复版则精确更新并验证；没有时评估经专项安全测试的解压器补丁/替换，或提交明确风险决策。不得自动采用 npm 建议的 Forge 6.4.2 大版本降级，也不得把“使用官方归档”写成漏洞已修复。隔离构建机与归档校验只是缓解措施。

修复后需复跑完整/production audit、Mac 打包与包内冒烟、Windows maker 和实际运行；当前 362 项桌面测试、类型检查、renderer build 均不代替这些验收。`npm ci --ignore-scripts` 跳过 Electron 下载及安装脚本，只证明锁定 JS 依赖树可安装，不证明发行包可运行。

## 同日Win只读复核补充

绑定 `14a082fed11afd01b073091eb416565f1ab0b373` 与lock blob `446e7786c2543c76c4fb508b85e36ceb7709d90b`；独立 `supplychain_readiness` 使用Node24.19/npm11.6.2再次核验：full audit仍17 high，production 0。runtime切片只改根engines，依赖节点不变，发行门禁不关闭。

更正前述上游现状：extract-zip仍无已发布修复版，但[Packager20.0.1](https://github.com/electron/packager/releases/tag/v20.0.1)已换用官方 `@electron-internal/extract-zip`，当前最新20.3.0。稳定Forge7.11.2仍要求Packager18系列；不能直接覆盖为Packager20或切Forge8 alpha并视为兼容。

待专项验证的最小候选是仅在 `@electron/packager@18.4.4` 父节点下，将extract-zip精确替换为官方 `@electron-internal/extract-zip@1.0.5`。本次只确认Packager调用形状和CJS默认导入可加载，没有修改依赖或执行解压/打包，不视为已修复。该包的[官方安全模型](https://github.com/electron/extract-zip/blob/main/SECURITY.md)要求校验过的可信Electron归档与干净目标目录，不覆盖任意不受信任ZIP及预置攻击者内容。

实施前后需保留公告反例、路径/链接/重复项及正常归档测试；锁定变更和两个audit外，还需Windows完整maker/包内及实际生命周期，以及同锁Mac Framework链接/权限、打包启动验证。audit归零不能替代以上条件，未批准豁免、自动降级或无关升级。
