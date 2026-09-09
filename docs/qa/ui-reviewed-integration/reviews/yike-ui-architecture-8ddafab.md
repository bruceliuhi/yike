# 原生运行时与包内冒烟修复：独立架构复审

日期：2026-09-10。候选：`8ddafab6cc4cea21c244dcf1f052bf04defe8e87`，基线：`a31069fead15f395e7b4ec93c9c91e441beea798`。范围严格限定这两个提交间的 **8 个文件**，审阅者不是这 8 个文件的作者。

**结论：源码架构 PASS，本次差量未发现剩余 P0/P1/P2。可以进入修复候选的最终构建、严格包内冒烟和原生验收。** 本文不提前批准尚在执行的新包/全量，不把源树审查当成原生运行成功，不关闭完整 UI Goal。

## 根因与修复判断

### React 单例

原失败 `29d93a50535cdd2cebc01304c4166d4fee8f3fc09a2184d43db2d736f06d21d6` 包的 renderer 存在两份独立 hook dispatcher；我此前直接检查其 `index-9H26hK5M.js` 得到两组 `useState` 工厂/不同的内部 H 容器。主线程模块图进一步证明 `node_modules/react` 与经自指软链接到达的 `node_modules/node_modules/react` 实际 realpath 相同，保留软链接路径后被当成不同模块。未把版本字符串重复或未知操作者猜测当作根因。

已安装 Forge 插件 `getConfig()` 默认 `preserveSymlinks:true`，最后 `mergeConfig(default,userConfig)`。`desktop/vite.renderer.config.ts` 显式设为 false 能覆盖该默认；`dedupe:['react','react-dom']` 进一步固定应用与组件库的 peer 依赖。没有将 React 改成外链或放松 renderer 沙箱。

新增 singleton 回归在独立临时目录建链接依赖与自指路径，通过实际生产 Vite 模块图证明旧配置产生多份 React、新配置只有一份；不是仅断言配置对象。`write:false` 不覆盖实际构建产物，清理限定该临时目录，未操作审核依赖链接或真实安装目录。

### Zod 与严格 CSP

`app/main.tsx` 第一条静态导入 `validationRuntime`，其唯一动作是 `z.config({jitless:true})`。读取当前锁定 Zod 4.4.3 源码可见：对象 schema 根据该配置禁用 JIT，走原解释校验；`allowsEval` 也在该配置下不进行 Function 探测。此初始化先于后续 domain schema 构造，不需要 `unsafe-eval` 或关闭 CSP。

本次独立子进程把 Function 构造/调用替换为计数并拒绝的探针，再导入真实 bootstrap：**动态代码尝试 0 次，合法值通过、非法值和 strict 额外字段拒绝**；不导入 bootstrap 的对照发生 **1 次**探测。工具输出 `49f03e`：

```json
{"jitless":true,"evalProbes":0,"valid":true,"invalid":false,"extra":false}
{"withoutBootstrapEvalProbes":1}
```

这是 Node 中的初始化/校验反例，不替代真实 Chromium CSP 的最终包验收。此变更没有改依赖版本、补丁化 node_modules、修改 HTML CSP 或业务数据 schema。

## 包内冒烟的失败边界

`packaged-smoke-policy.mjs` 与 runner 修正了原来两个独立的假通过来源：

- Electron 43 首参数为带 `level` 的事件对象，第二参数是旧数字级别。现在兼容读取真实错误事件；同时记录 preload 错误与 renderer 进程退出。
- 检查真正 `main#main-content` 下唯一工作台 h1、可用创建按钮及公开样例区域/按钮，并拒绝页面错误边界。错误页的“返回商机工作台”文字不能再满足条件。

真结构必须连续三次观察成立，在导出检查后再次核对；已捕获的错误不会被后续页面恢复抹掉。主流程检查完成、第二次退出确认和最后错误检查通过后，才在唯一临时目录写 `completed.json`。父进程同时要求子进程退出 0 和完成文件为 true；提前干净退出、异常或超时均失败。没有因 `app.exit(0)` 就宣称冒烟成功。

真实 Electron 负例测试包括原坏 ASAR、提前退出 0 和 renderer console.error。负例开关/旧 ASAR 缺失时明确 skip，不伪造通过；临时测试 ASAR 不进入产品。原有 IPC、临时文件导出读回和取消、取消退出后确认退出检查保留。

这里验证的是已定义的工作台启动结构及技术冒烟；它不自动证明按钮点击后的全部路由、任务输入、所有页面或系统原生文件选择器已验收。完成文件也只是测试过程完成证据，不是签名供应链证明。

## 独立验证与未执行项

从候选所在目录使用 Node 24.19.0 独立执行：

```sh
vitest run tests/packagedSmokePolicy.test.mjs tests/rendererReactSingleton.test.ts
```

实际 **2 文件、14 passed、0 skipped**（工具输出 `197dc8`），包括旧链接配置反例与修复配置。另有上述 Function 拒绝探针。8 个被审文件在读取/运行时与提交一致，限定源码差量 `git diff --check` 通过。

未重复主线程全量、类型检查或 Peirce 的真实 Electron 负例运行，不将其口头结果算入本次独立测试数。未启动新浏览器、未重建/运行当前新 ASAR，未修改源码、依赖或其他审核报告；原工作树另有原始候选接入文件和 QA 文档，不属于本次源码批准。

## 交付仍须满足

1. 原 29d 包必须保留为失败证据、停止作为可用候选交付；其旧 smoke PASS 已被实际原生异常推翻。React-only 过渡包也不能替代最终含 Zod bootstrap 的包。
2. 最终 8ddafab 构建需记录新的 ASAR/ZIP 摘要和输入绑定，并用严格 smoke 通过；旧坏包应被同一新版 smoke 拒绝。随后以最终包做冷启动、实际页面/表单交互和正常退出/重启的可见验证。
3. 原测试集合、修复差量和正在执行的全量分别记录，不相加；跳过项、首次故障和 CSP 探测失败不删除或回填成成功。
4. Windows 当前候选的实际构建/安装/缩放/卸载、真实平台服务、全部状态视觉及完整 Goal 仍按独立证据推进。此源码 PASS 不代表这些项目已经完成。
