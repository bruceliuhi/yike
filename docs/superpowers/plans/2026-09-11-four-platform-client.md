# 知乎接入普通任务与监控

> For agentic workers: executing-plans、定向TDD、一次非作者整批审核。复用已批准V0.2多平台方案和现有R3/R4页面，不新增布局或发送授权。

**Goal:** 已接好的知乎原生源通过现有账号、能力、单次任务及持续监控进入普通客户端。
**Architecture:** 新增显式four-platform-foreground-v1/four-platform-monitor-v1；旧xhs/three模式不扩大。复用原账号隔离、START/CLAIM、共享预算、结果上传、原请求恢复；不开公开网站或知乎发送。
**Tech Stack:** 现有Python policy、TypeScript/Zod/controller/renderer，无新依赖、DB迁移或重写连接器。

## Task 1: 服务端能力与桌面消费

- [ ] 修改pilot/foreground_collection.py及monitor_runtime.py：four策略复用three的配置校验，但仅显式允许ZHIHU；support精确返回对应mode，旧mode仍拒绝知乎。新tests/test_four_platform_policy.py验证新旧模式、非法配置、监控schedule和support。
- [ ] 扩展desktop/src/shared/platformAccount.ts的知乎正ASCII uid，foregroundCollection.ts允许four模式/4binding，同时禁止旧three携带知乎。main/foregroundCollectionController.ts、monitorCollectionController.ts、pythonCollectionDriver.ts复用原流程，能力枚举及START/监控启动均按mode检查知乎，不能仅靠renderer过滤。
- [ ] renderer/services/platformConnection.ts、domain/task.ts、domain/monitorCollection.ts接知乎映射和four绑定；现有账号/任务页面沿用，平台连接不等于采集成功。
- [ ] 在现有foregroundCollectionController测试fixture添加知乎四平台能力与原生派发及旧模式拒绝案例；新增小型shared/renderer测试核对uid、四绑定、原监控目标映射。不重跑全套。

## Task 2: 收口和下一里程碑

- [ ] 定向Python、受影响desktop测试和一次类型检查；必要独立整批审核，修复只测差量。复用8cf9971依赖patch重放/原生测试证据，不重验相同源码。
- [ ] 更新唯一任务书与部署配置说明，正常推main。真实搜索/入库/UI详情仍须同版本Windows包和授权服务账号，不能用合成controller结果标完成。
- [ ] 接续服务地址的可分发配置与一次Windows候选构包/实测。该项是下一里程碑依赖，不为本批政策接线造假完成；完整V0.2目标保持。
