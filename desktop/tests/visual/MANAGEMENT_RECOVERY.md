# P18 TEST 管理生命周期

入口：`http://127.0.0.1:18794/?scenario=P18&state=populated&management=lifecycle`。

仅这个显式参数组合及 TEST 登录身份启用。默认 P18 的只读状态夹具不变；`empty/error/loading` 或其它页面不能借参数开启。左下角“TEST 场景”中的管理控制决定**下一次**保存、执行、原请求查询或取消回执，不直接清除页面的未决记录。

所有状态、导出内容与回执仅保存在本实例内存。页面中的“已保存/已完成”为真实页面处理 TEST 回执后的文字，**没有创建文件、恢复客户库、绑定设备、下载安装包或调用后台**。固定横幅与控制区一直说明 TEST 语义；此项不替代原生保存选择器验收。

## 三条核验路径

1. **导出与保存回执**：展开 TEST 控制，保持保存回执“取消保存” → 产品页“导出数据” → “生成并保存 CSV”。控制区显示模拟取消，产品页不能提示已保存。再选择“内存模拟已保存”并点同按钮，产品页才显示已保存；选择“保存失败”重试，应显示保存错误。CSV/备份内容先经过真实 `downloadText` 校验，仅走 TEST `saveExport` 内存桥；不会触发文件保存窗口或浏览器下载。
2. **恢复及原请求核对**：产品页“备份与恢复” → 选择本目录 [TEST-management.yike-backup.json](TEST-management.yike-backup.json) → “检查影响并预览” → 核对 TEST 空间/版本/影响 → 勾选并“恢复客户数据”。默认执行/查询都为 UNKNOWN。关闭弹窗后仍显示待确认操作；清本机草稿不释放原操作。先“核对原操作”仍未知，再把 TEST 原请求查询改为“确定未执行”或“仅内存完成”，重新点产品页“核对原操作”后才获得终态。只改变下拉框不能解锁，也不发第二次执行请求。
3. **取消尚未确认**：执行回执保持 UNKNOWN，打开“检查更新” → 在上方下载新版本区域“检查影响并预览” → 勾选 → “下载安装包”。关闭弹窗，点待确认记录“取消下载”；默认取消回执 PENDING，原锁仍在。将 TEST 取消回执改成“确定已取消”，再次点该原请求的“取消下载”，才能清锁。取消只接受已记录的下载请求，不能拿恢复操作当下载取消。

计划有效期 60 秒。过期后重新预览，不能把旧计划当有效。恢复文件仅接受契约格式、相同 TEST 空间及 `TEST-` ID 的合成记录；真实客户内容和敏感字段不应放入此夹具。原请求 ID/计划、输入摘要、备份全文摘要及账户 revision 均核对；旧终态不会被后来改变测试选择器反转。

关闭弹窗/切路由可检验页面重入；刷新页面会重建内存与测试存储，**不能当作后台持久化验证**。未知原请求不会被新实例猜成完成。

## 隔离与回归

- 实现：[managementRecovery.ts](managementRecovery.ts)、[ManagementRecoveryControls.tsx](ManagementRecoveryControls.tsx)。沿用生产 `ManagementService`、schema、影响确认、ledger、保存结果及 Settings 组件。
- [isolation.ts](isolation.ts) 默认移除 native bridge；只有本场景可传入仅含 `saveExport` 的冻结 TEST 对象，没有其它原生能力。网络、XHR、外链、剪贴板、浏览器下载与持久存储隔离保持。
- 文件全在 `desktop/tests/visual`，生产 renderer 无导入。生产打包排除仍须由实际生产图检查记录，不能用 TEST 构建宣称生产排除通过。

定向命令（desktop 目录）：

```sh
npx vitest run tests/visual/managementRecovery.test.ts tests/visual/managementRecovery-ui.test.tsx tests/visual/isolation.test.ts
```

包含实际 Settings + downloadText 的取消/成功/失败、恢复 UNKNOWN 重入与清草稿、取消 PENDING/终态、原请求幂等、错空间/摘要/版本/文件、过期和登出拒绝、仅 TEST 保存桥与原隔离不回退。不执行真实管理操作。
