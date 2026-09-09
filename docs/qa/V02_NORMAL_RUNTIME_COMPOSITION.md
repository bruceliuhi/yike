# 正常服务启动装配：验收记录

日期：2026-09-10。基线 `4cb9524`，计划认领 `4101379`，核心 `bc6a5b6`。依据[计划](../superpowers/plans/2026-09-10-normal-runtime-composition.md)和[部署契约](../contracts/V02_NORMAL_RUNTIME_COMPOSITION.md)。当前记录包含实际实现及测试；独立审核和推送另行记录，不预写通过。

## 已复现的问题

原 `pilot/cli.py:web` 只向 `build_app` 提供 `PilotStore`，已实现的策略/执行/候选/复核服务仅在明确注入时可用。根代理用普通 CLI 构造真实 FastAPI，替换的只有 Uvicorn 启进程与测试应用 DB 选择；HTTP、身份、存储与受限 PostgreSQL 均实际运行。

```sh
uv run --frozen pytest -q tests/test_pilot_runtime_http_postgres.py
```

实现前 **1 failed / 1.21s**：认证后 `/api/ui/research-strategies/prepare` 返回 `501 capability_unavailable`，预期 200。测试数据库配置仅在进程环境中注入，不留存连接或登录态。不是缺数据库、错误 fixture 或外部平台造成的失败。

## 接收边界

验证实际普通入口的服务组合、同应用 DB、策略写/读绑定、原请求恢复、模型配置与无配置拒绝；本地 HTTP 供应商响应和签名来源输入是明确合成测试数据。签名来源由受信 fixture 预置，普通入口不接收其放行回调。不得将该链路写为真实平台采集、模型商业效果、正常短信登录、已发消息或客户转化。

本片不修改 SQL/桌面/source worker，不重复未变代码的全量回归或原生构包。必要定向测试、独立任务审核和整片集成审核仍执行。

## 核心实现和定向测试

`bc6a5b639ed65920a7b1174b1aae07aeb51eed68` 仅改4个文件：新 `pilot/runtime.py`、对应纯测试及既有 CLI/Web-start 测试。五个真实服务复用同一应用 DB 和策略实例，普通入口接线；配置全无仍可启动，部分/非法配置报固定错误，误带非空管理员URL拒绝。没有新增框架、迁移、来源 policy 或能力开关。

实现者先观察原CLI6项通过；新增测试后 **16 failed / 4 passed / 0.39s**，为缺失 runtime 模块/CLI factory；最小实现后 **20 passed / 0.39s**。自审后的覆盖命令：

```sh
uv run --frozen pytest -q tests/test_pilot_runtime.py tests/test_pilot_provision_cli.py tests/test_candidate_assessment_model.py tests/test_pilot_web.py tests/test_ui_api.py
```

实际 **262 passed / 5.35s / 0 skipped / 0 failed**。同实例绑定、默认关闭、配置组合与错误不含值/异常链、构造不联网、原Web代理限制与现有模型/HTTP行为均纳入；与下面根代理PG集合分开记录，不作为平台数量或全仓结论。

## 根代理普通启动验证

首次接入新装配后 **1 failed / 1 passed / 3.62s**：主链已完成确认、分析、纳入、固定证据和策略撤销，后续历史查询返回422。按系统化排查核对既有 `candidate_review_api.py` 的请求合同，原请求历史模式要求 `page=1&pageSize=1`；新测试漏传后一项而使用默认20。只补测试请求参数，不放宽生产校验。

相同两条测试重跑 **2 passed / 4.71s / 0 skipped**。已验证：

- 通过普通 CLI 实际准备/确认/读取/撤销策略，真实受限 PG 持久化；不是替换业务服务的假启动器。
- 可信测试 fixture 预置签名合成来源后，普通入口能读原始与待审候选，调用环境配置的实际模型适配器、所属子进程和本地 HTTP 供应商，人工核验、INCLUDE、读取固定原文证据。
- 同一分析请求重放不再次调用模型；列表、健康检查、历史原请求恢复与商机读取不调用模型，整条链本地供应商只收到一次请求。
- 当前列表使用真实策略 snapshot reader；撤销后旧判断失效，但原历史回执和纳入时证据保留。其他候选 owner/tenant 不可读，退出后的凭据拒绝。
- 未配置模型的 ASSESS 与缺真实来源 policy 的有效签名 START 均返回501；拒绝 START 没有成功执行回执，未产生分析记录；能力声明保持关闭。

以上不是实际外部来源、短信收码、桌面回源、商用模型效果或确认后发送验收。只读 `/readyz` 通过仍仅意味着数据库可连；测试角色的非超级用户/非绕过RLS属性不能替代目标部署核验。

根代理随后执行本片及相关实际 HTTP 组合：

```sh
uv run --frozen pytest -q tests/test_pilot_runtime_http_postgres.py tests/test_confirmed_strategy_http_postgres.py tests/test_candidate_review_http_postgres.py --tb=short
```

结果 **9 passed / 15.62s / 0 skipped / 0 failed**。包含上述2项，不能相加；原策略/签名/模型子进程 HTTP 契约保持通过，没有再次跑无关桌面、打包或全仓测试。
