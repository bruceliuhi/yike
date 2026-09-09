# 8ddafab 冷启动修复独立质量复核

日期：2026-09-10。绑定候选 `8ddafab6cc4cea21c244dcf1f052bf04defe8e87`，比较基线 `a31069fead15f395e7b4ec93c9c91e441beea798`。

**限定 PASS，可合入此候选：本次 8 文件范围未发现剩余 P0/P1，前次“页面未能打开”的原生启动交付 P1 已对最终 `aec0b946…` 包关闭。** 已核对该包的原生工作台、真实退出警告、继续编辑保留草稿、明确放弃及同目录重启草稿清空证据，并独立检查当前重启进程的实际可执行文件和 ASAR。此结论不扩展为整体前端 Goal 或商用验收完成。

## 独立代码复核

本次只读审核 root 的 renderer 配置、验证 bootstrap、React 链接布局回归，以及另一审核者的 smoke 脚本、策略与负例测试。没有修改源码，也没有自批此前本人编写的 Windows 脚本或其它原有业务模块。

- `vite.renderer.config.ts` 显式 `preserveSymlinks:false`、dedupe `react/react-dom`，修复应用与 react-dom 通过不同符号链接路径载入多份 React 的问题。回归在独立临时目录重建链接布局，旧配置产生多于一份 dispatcher 模块，新配置仅一份；不是只检查配置字面值。
- `main.tsx` 首先导入 `validationRuntime.ts`，在域 schema 加载前启用 Zod `jitless:true`。仅改变验证运行方式；未添加 `unsafe-eval`，生产 `script-src 'self'` 等 CSP 未放宽。
- smoke 改为检查主内容区唯一工作台标题、创建入口、公开样例标题及可用入口，显式拒绝 `.page-error`，连续三次成功后才继续，并在导出后再检查。固定侧栏文字、错误页“返回商机工作台”以及单纯加载壳不能再满足旧断言。
- console error 同时处理 Electron 43 事件对象和旧数字等级；preload error、renderer 进程退出均失败。只有完整执行退出确认阶段并写出完成标记后才允许成功；提前退出码 0 不再算成功。
- 新负例覆盖旧真实坏包、真实 Electron renderer `console.error`、未做检查即退出 0；策略测试覆盖错误页、旧内容旁出现错误页、缺失/禁用操作及已序列化 DOM 检查函数。未将负例 fixture 当作产品功能。

## 测试与证据

本审核独立执行：

```sh
cd /Users/bruce/Developer/work/yike-ai-product-design/desktop
PATH=/Users/bruce/.nvm/versions/node/v24.19.0/bin:$PATH npx vitest run tests/rendererReactSingleton.test.ts tests/packagedSmokePolicy.test.mjs
```

结果 **2 文件 / 14 passed**。另在独立 Node 24.19 进程先将 `Function` 替换为抛错探针，再导入实际 `validationRuntime.ts`；合法对象通过，非法值和多余字段拒绝，`evalAttempts=0`。该检查验证解释执行保留基础验证能力，不替代所有业务 schema 测试。候选差异 `git diff --check` 通过。

[fix](/Users/bruce/Developer/work/yike-ai-product-design/docs/qa/ui-reviewed-integration/fix) 原始日志记录：定向 5 文件 / 24 passed，smoke 负例及策略 2 文件 / 16 passed，最终受控全量 **87 文件 / 944 passed / 21 skipped**，typecheck 无错误，严格 packaged smoke PASS。本审核已读日志但没有重复全量；这些范围重叠，不能相加。21 项跳过不计为通过。

## 最终包一致性

独立将提交的全部 284 个受控 desktop 文件与当前文件逐字节比对，均一致；同时核验 `source-binding.json` 的完整集合、SHA-256 和 Git blob，未发现缺失、多余或不匹配。desktop tree：`54d1c0a0a8b7d72969f3c59943dc95b4a3d935b6`。

当前 39 个构建文件与 ASAR 对应文件逐字节一致，36 个 renderer 资源哈希与清单一致。ZIP 内仅一个 `Contents/Resources/app.asar`，其字节与下列 ASAR 一致。

| 产物 | 字节数 | SHA-256 |
| --- | ---: | --- |
| 最终 ASAR | 1,769,109 | `aec0b946be4ca147e940e3c4ec1f3c0652104585be843ff69ebf95f2869da50d` |
| 最终 Mac arm64 ZIP | 122,472,470 | `c4b179b7e491ff872cdb809f20c555fe4dc5c1d4819ad16a6c09b5e9961f96a2` |

ASAR 目录未发现 tests 或四个未提交 raw 模块；生产图日志记录 4,760 个模块、排除项命中 0、React 生产模块仅一份。四个 raw 草稿仍不计为候选功能。源码清单保持“构建后核对”措辞，不宣称依赖完全无改动、干净构建前后取证或可重现构建。

## 原生验收与历史边界

- `initial-a310` 的 `29d93a5…` 为已实际失败的坏包；保留原 smoke PASS 及失败证据，不重新解释为可交付。
- `react-only` 的 `befacea…` 为仅修 React 的中间包。其原生草稿退出重启链属于该包；其严格 smoke 曾因 Zod eval probe 的 CSP error 失败，不作为最终产物的通过证据。
- 本审核已实际查看最终 `fix/native-workbench.png`、`native-quit-warning.png`、`native-continue-preserves-draft.png`，并读取对应 AX 文本。图中为未配置客户服务的实际客户端：工作台完整显示，存在真正的原生退出警告；继续编辑后任务名“最终包验收”和 50 搜贝上限仍在，状态为本机草稿、未启动。未显示采集、计量或发送成功。
- 部分 `.txt` 是 AX 增量/“无变化”响应，不是完整页面树；可见状态以对应实际截图及有内容的增量共同说明，不能冒称每份 txt 独立覆盖所有字段。
- 最终包 [native-lifecycle.md](/Users/bruce/Developer/work/yike-ai-product-design/docs/qa/ui-reviewed-integration/fix/native-lifecycle.md) 记录初次 PID 1244 明确放弃后退出码 0（主线程实际 exec `4363c0`）、同 userData 目录再次启动。本审核实际查看最终 `native-restart.png` 并读完整 `native-restart.txt`，确认为线索采集页“本机草稿 0”，无刚才的验收任务；`native-restart-workbench.txt` 记录重启工作台。
- 独立实时 `ps` 与 `lsof` 核验重启 PID 6850 存在，命令与 `native-process.json` 一致，实际打开的 executable 为此构建 `.app/Contents/MacOS/YikeAI`，cwd 为当前 desktop；重新计算旁侧 ASAR 字节仍为 `aec0b946…`。该取证限进程/路径/当前包字节；并不虚称操作系统始终保持 ASAR 文件句柄或记录了初次进程所有历史状态。初次退出结果采用主线程实际工具记录，审核者未重复操作界面。

最终目录 README 已准确区分初次坏包、中间 React-only 包、最终包以及尚未执行范围。任务表单另有既存无障碍标签在可见“读取失败”时仍含“读取中”的后续 05A 修正项，已明确保留；不算当前 8 文件修复已解决，也不影响本次冷启动修复判定。

smoke 仍使用临时 userData、隐藏的测试 Electron 进程和替代保存/退出 dialog；其临时文件写入是真实 IPC/磁盘路径，但不等于实际原生保存选择器或用户操作验收。Windows 实机、签名/公证、客户后台与平台接入、真实研究/搜贝消耗/触达回复等不在本次通过范围。前端整体 Goal 不能因此标完成。
