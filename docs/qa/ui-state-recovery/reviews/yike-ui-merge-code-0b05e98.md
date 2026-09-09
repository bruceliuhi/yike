# 0b05e98 双亲合并增量代码复核

- 合并提交：`0b05e98926e7e18858f0ab8e5780e49a3500ab4c`。
- 第一父提交：`a25ba7b331e7712c4fba53b173cbbc704ec3e734`。
- 第二父提交：`22bae220251f5c3168faa889cc42fa02ea74fa74`。
- 共同基线：`1c56fc5734c738558067979c99c2fdd23d307552`。
- 结论：本次合并增量 PASS；未发现因合并新增的 P0/P1 或需要退回合并的具体缺陷。此结论不批准当前仍在修复的 P14/P15 跨空间问题，也不是最终发行或生产能力验收。

## 复核范围与发现

1. 对双亲分别比较：双方同时修改仅 `desktop/src/renderer/pages/TaskWizard.tsx`、`desktop/tests/visual/main.tsx`、`desktop/tests/visual/README.md`。所有仅一方修改的文件在合并提交中与对应父提交逐字节一致；没有丢弃其它材料、触达或安全壳改动。`git diff --check a25ba7b 0b05e98` 通过。
2. TaskWizard 相对远端父提交只有既有平台可见状态/AX 名称统一差异（690–711 行）。新策略准备、确认、用量与原启动恢复代码未被冲突覆盖。该 AX 修复是本审核者此前作者范围，此次仅确认合并保留，原修复非作者审批仍归 root/其它独立审核。
3. 搜贝仍按用户草稿中的 `research.maxSoubei` 与来源/时长/模型次数上限映射；`domain/researchStrategies.ts:52–63` 保留这些值。新增技术执行上限独立设置、显式采用建议，不以搜贝换算，也不在缺值时默写默认执行许可。P19 的准备回执 ID、策略 ID、配置摘要、画像摘要和当前草稿/执行上限参与人工复核绑定（TaskWizard:140–160）。
4. 不暗启动：新策略服务存在时，页面始终显示签名执行未接的阻断，`start()` 也在派发前直接返回（TaskWizard:357–365）。确认、原请求查询和撤销均由用户事件触发；挂载、刷新或历史查询不自动恢复人工勾选。原请求控制器在 POST 前持久记录，精确绑定用户/空间/空间版本/草稿；只有明确 request_not_found/404 且原请求摘要一致时，显式重试才沿用同 UUID。旧服务注入路径保留原用量与执行门禁，不能借新策略确认绕过旧启动锁。
5. 来源边界：两类来源输入和日程均保留在策略快照；非生效输入明确标注保留但不执行。现有 `provenance`/`coverageProvenance` 仍保留在原草稿，适配器对不支持的来源谱系直接拒绝准备（domain/researchStrategies:46–51），没有剥离谱系后提交普通研究的静默降级。策略快照确认不是原文来源核验，也不是已执行、已计量或已触达证据。
6. TEST 合并入口（visual/main:26–30、134–138）同时保留材料恢复、管理恢复和策略确认；策略场景限定显式参数、P06/P19/P20、populated、非 guest、非 recovery。没有改动生产导入；这些内存行为不作为真实后端或发行包验证。

## 实际定向验证

Node 24.19，desktop 下运行：

```text
node node_modules/vitest/vitest.mjs run \
  tests/ui/task-wizard.test.tsx \
  tests/ui/strategy-confirmation.test.tsx \
  tests/ui/strategy-confirmation-hook.test.tsx \
  tests/ui/strategy-execution-limits.test.tsx \
  tests/ui/r4-research-usage.test.tsx \
  tests/visual/strategy.test.ts \
  tests/visual/materialRecovery.test.ts \
  tests/visual/managementRecovery.test.ts
```

结果：**8 文件、114 passed、0 failed、exit 0**。日志 `/tmp/yike-merge-0b05e98-tests.log`；实际耗时 2.45 秒。对应审核文件与提交相同；并行工作树的 Followups 4 个在途修改未纳入本结论。

未重复 Windows 全量源码审查、PG 集成测试、全套前端测试、构包或原生可见验收。a25 包仅绑定 a25，不能覆盖此合并。四个 untracked raw-candidate 草稿未纳入提交或本次批准。
