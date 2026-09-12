# 设置页设备状态澄清实施计划

Goal：消除商业绑定未知与本机身份状态的混淆，不改变认证。

Architecture：Settings复用useResource的代次/超时保护与DeviceIdentityPanel固定标签；getStatus只读，旧账号/旧弹窗请求不能覆盖新状态。

Tech Stack：React、TypeScript、Zod、Vitest。

按用户快速验收要求，主任务串行实现，独立Agent一次差量审核，不重复构包。

- [x] tests/ui/settings.test.tsx：新增只读READY/待核验、坏DTO、未知商业状态及关闭弹窗刷新测试，先运行RED。
- [x] pages/Settings.tsx、pages/settings/DeviceIdentityPanel.tsx：复用安全标签、只读取得状态、固定失败/未知文案；不修改prepare门禁。
- [x] settings/panel定向测试及类型检查；独立审核通过后提交main，未改变management实现。
- [ ] 下一次必要候选再纳入；当前0d9500b继续实机验收，不追认新UI已安装。

## Evidence

2026-09-13：初次4项RED后20项GREEN，追加账号切换/未登录2项通过。独立首审发现同user切空间或同bridge换service未失效的P2；新增空间ID、version及service三项均先RED（3失败），补齐useResource依赖后最终settings/panel **25 passed / 0 skipped**，Node24.19.0的tsc --noEmit exit0。最终结果去重25项，不累加重复运行；本地证据 `.runtime/device-status-clarity-review-{red,green}.json`，原始失败保留。

profile_rescan_review差量GO，绑定Settings `86d479aaff4a39f6056332bab13b5a81b8b07677`、Panel `c04d944c2eee2151e4c12109b6e7ee45e129a505`、Tests `52a1390f3f14e2936a637e708312039cc28c0301`。没有自动认证、生产部署或新构包；当前已安装0d9500b不包含这批显示调整。真实平台认证/采集/人工批准联系/客户验收未完成。
