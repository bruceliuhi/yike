# UI 候选增量独立质量复核

日期：2026-09-10。候选 **`e70c3a1d048f0f3d6b13bf74805eb60ad4a587cf`**，父提交 `99993552f1559681c8f671a57096ec23d4e9095b`，完整范围基线 `a77e5828de9ecb0f3c9b60dfcebf56c96685d9bc`。冻结树：`/tmp/yike-ui-review-20260910`。

**结论：本次限定质量范围 PASS，当前未见剩余 P0/P1，可合入源码。** 父候选的会话退出、P09 画像版本、P20 日程、连接读取与账户隔离审核结果可继承，本次连接旧解析路径修复另经实际复核。不能将此结论视为新安装包验收或完整前端 Goal 完成。

## 差量与实际核验

`git diff 9999355..e70c3a1` 仅有三项：

1. `desktop/src/renderer/domain/connectionDisconnect.ts`：在旧 Zod 模型解析前拒绝任何含 `registration` 的对象，避免解析器剥离设备/连接版本信息后错误按旧平台级身份核对。拒绝发生在读取预检/核对路径上，既不会派发新断开，也不会用另一设备的已断开记录清除原请求。
2. `desktop/tests/ui/connection-disconnect.test.tsx`：两种预检状态 CONNECTED / DISCONNECTED 均拒绝，断开未调用、ledger 未新写；原 ACKNOWLEDGED 请求遇带设备版本的响应仍保留、无成功通知。三项通过真实页面与共享操作记录路径断言，并非仅匹配错误文字。
3. `docs/qa/ui-connection-registry/review-fix.log`：单列本次 3 文件 / 36 passed 的主线程记录，没有覆盖此前失败或夸大为又一次全量。

未包含新的原始候选模块或其他产品源码改动。源/测试 diff 检查通过。

独立使用 Node 24.19.0，在冻结目录实际执行：

```sh
npm test -- tests/ui/connection-disconnect.test.tsx tests/ui/connection-registry-client.test.ts tests/ui/connection-registry.test.tsx
npm run typecheck
```

结果 **3 文件，36 passed / 0 failed / 0 skipped**；类型检查通过（工具 `ceb02f`，00:59:01）。与主线程日志一致。父候选独立 9 文件 / 109 passed 仍保持原提交绑定，不相加为新候选全量数量。根据主线程要求保留共享 `desktop/node_modules` 临时链接供另外两名审核者使用，未编辑源码或提交。

## 包与证据的适用范围

父质量报告原样保留在 `/tmp/yike-ui-quality-9999355.md`。其中核验的 **ASAR `6e2edbd31e149fce621311f2eed26845deee9bc4eae7ae4bf746c79a654f5427`、ZIP `780ac67bfde60adebaa0ccf68b36c9e3956736e0cc676c076914f0b831cf834c` 和 279 项输入清单只属于父候选**。

本次实际将该父输入清单与 e70c3a1 比对，恰有两项不一致：上述 `connectionDisconnect.ts` 与 `connection-disconnect.test.tsx`（工具 `82eb4d`），符合源码修复范围。不能再声称 279 项全部与新候选一致，不能声称旧 ASAR 包含新 registration 拒绝。主线程须在合入后重建、绑定最终 SHA、核对新包输入/ASAR/ZIP并执行相应包验收；本报告没有提前记为完成。

父报告对原生证据的区分继续有效：完整退出取消/保留/放弃/重启链属于更早 `614396…` 包，导航修正和最新连接包各有其有限页面/冒烟证明。图中 TEST 数据、模糊最小窗口截图、未显示长页底部及真实服务未配置等边界均未因本修复消失。

## 完整候选的限定批准

源码合入层面，本次身份拒绝修复已覆盖新旧读取契约交叉路径；父候选其余已审内容未变，本质量范围无剩余阻断。本人此前编写的 Windows 脚本仍明确交由其他审核者批准，不在本次自批。

继续保留：新包重建与版本绑定、相应原生完整交互、真实文件保存/取消、P04/P14/P15/P18 剩余状态；真实受限 PostgreSQL/登录会话的连接读取、平台能力/版本化断开、调度/搜贝/消息服务；Windows 新候选安装、退出、重启、卸载及100/125/150系统缩放；签名、公证和原生产恢复门禁。整个前端 Goal 与产品上线均未由本报告关闭。
