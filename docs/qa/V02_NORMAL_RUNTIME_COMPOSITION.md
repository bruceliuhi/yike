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

根代理自审另将“未写入分析记录”的检查改用受信测试连接直接计数，避免未设置身份的RLS空结果形成虚假证明；普通服务仍只用受限角色。只重跑本片2项，**2 passed / 4.26s / 0 skipped**，生产代码仍为冻结的 `bc6a5b6`。

## 并行工作保留

已正常合入Win `a9d18db`，合并为 `fad2d24`，新增仅设备签名客户端计划/分工，不改变本片生产代码。root读取完整新增计划与交接，确认Win承担05F持钥/来源链；Mac接收其执行签名payload最小接口请求。不是Win已接收本片运行效果，也不是设备/平台功能已经完成。

`secret_scan.sh` clean；本片与部署文档17个相对链接有效，增量 `git diff --check` 通过。目标环境角色、真实来源/模型、客户安装和生产验收仍未执行。

## 独立任务审核

非作者 `normal_runtime_task_review` 对 `4101379..bc6a5b6` 四文件审查：**规格符合 / 质量批准，Critical、Important、Minor 均0项**。核对同实例接线、配置原值/安全错误以及既有模型调用入口；未复跑实现者262项，不能把该数字称为审核者实跑。

审核要求由根代理补充真实PG/HTTP、只读不调用模型与角色边界：本页根代理9项及最后2项给出相应普通入口证据；真实部署角色/来源/收发仍未验收，明确不纳入本片完成声明。整片代码/架构/质量终审与远端推送尚待另外记录。

## 整片终审发现：容器缺少规则资源

`normal_runtime_final_review` 对精确 `a9d18db..ebd51e1` 完整增量给出 **REQUEST_CHANGES：0 Critical、1 Important/P1、0 Minor**。根代理补查 Docker 布局提出风险，独立审核者确认：现有镜像 `uv sync --no-install-project`，只复制 pilot/migrations/static；既没有 wheel 带入的 `pilot/_assessment_rules`，也没有源目录规则。新装配配置模型后，构造即读取规则，因此源码链可通过但此镜像启动会失败。

该结论不是重复源代码测试能消除的。按计划补充限定修正：镜像只加入已有两份版本化规则；用隔离的真实 COPY 布局执行普通启动与规则摘要比对。没有修改规则内容、模型行为或扩大来源权限；修复和差量复审前不放行本片。未执行实际 Docker 构建、Linux 镜像运行或生产部署。

修复为 `68bec6c`，测试隔离加固 `e550f6165f39489bc6a2dd9f2e4ff9001d25ab51`。只有两条 Docker COPY 和一份新测试；模型、runtime、SQL、规则内容、依赖和桌面不变。测试按 Docker 的实际字面 COPY 声明复制到临时目录，独立 Python 进程限定并断言从该目录导入 CLI，真实执行 `web()` 构造、捕获交给 Uvicorn 的 FastAPI；版本/摘要必须等于原规则。禁止 socket/数据库连接，仅用合成配置，不能退回开发仓库掩盖缺文件。

- RED：**1 failed / 0.51s**，隔离目录实际普通启动抛出 `invalid_assessment_configuration`。
- 增加两条 COPY 后：**1 passed / 0.51s**；补进口来源断言/无外连保护后最终 **1 passed / 0.52s**。
- 最终限定覆盖 `uv run --frozen pytest -q tests/test_pilot_runtime_container_layout.py tests/test_deploy_contracts.py tests/test_pilot_runtime.py`：**18 passed / 0.70s / 0 skipped**。
- 根代理对冻结 `e550f61` 单独执行布局测试：**1 passed / 0.53s**，凭据扫描 clean、增量格式检查通过。没有重跑未改业务的PG或客户端。

这些集合重叠，不相加。证明的是宿主 Python 下的 Docker 声明文件布局和正常模型构造，不是实际 Linux 容器、生产用户权限或外部服务验收。P1是否关闭以随后独立差量复审为准。

## 独立复审收口与并发整合

`normal_runtime_final_review` 完整读取修正差量 `ebd51e1..d100cdfdd2b3761d1f41a50b4515a4160e6bc20a` 后给出整片最终结论：**PASS；原容器资源P1关闭，0 open Critical、0 open Important、0 Minor，可正常集成/推送，不是生产或完整V1验收。** 审核核对实际COPY、忽略规则、固定加载位置、隔离导入与CLI回归；未代替作者复跑测试。上节原REQUEST_CHANGES和RED历史保留，不追改为最初已通过。

收口时收到Win设备持钥/签名模块 `ff623eda1d7c037a279517ca668ecc467af0cecc`，正常合并为 `6b5e7e43d37fb87760489aa482bdde0016c8f340`，无冲突。根代理核对本片4个核心文件与 `bc6a5b6`、Docker/隔离测试与 `e550f61`、desktop/migrations与Win来件逐字一致。来件原Windows原生证据见[Win验收](V02_DEVICE_SIGNING_CLIENT_WIN_REVIEW.md)，不写成Mac本次实测。

Mac对合并快照实际运行Win受影响的6文件 `deviceProof/deviceProofSigner/deviceKeyVault/serviceClient/servicePolicy/windowPolicy`：**97 passed / 567ms / 0 skipped**；`tsc --noEmit` exit0。这是同一集合在另一机器的交叉检查，不与Win的97项相加；未重跑无变化PG、全仓、安装包或原生OS保护。来件代码/架构兼容性独立复核另行记录，设备HTTP/真实平台启动尚未因此接通。

`normal_runtime_preflight` 完整静态审查Win `a9d18db..ff623ed` 的13文件，核对既有设备及执行协议和主进程隔离，给出**限定PASS，0项发现**；没有重跑测试或Win原生探针。BIND/PROVE签名器不用于执行签名域，尚未接产品HTTP。报告另复核 `369a049` 的4行测试差量，限定PASS。

推送前再次收到正常主线 `27ed499`，含独立交付的资料/联系草稿/跟进状态恢复及其已有审核证据，见[该片验收](ui-state-recovery/README.md)。正常合并为 **`a8f895a`**；唯一任务书文本冲突保留双方完整进度，无源码冲突。desktop与 `27ed499`、本片后端/迁移/部署/测试/规则与 `d100cdf` 分别逐字相同，不重新构包或将其他作者的全量、可见验收写成本机本次执行。

原 `6b5e7e4` 的凭据扫描实际失败：命中Win测试中PEM头格式断言，不是真实私钥。远端 `369a049` 已改为实际解析后重新导出PKCS8逐字比较，合入后 `secret_scan.sh` **clean**；未放宽扫描规则，也不回填旧树为通过。合并快照 root 实跑 `deviceKeyVault` 及本次UI变动相关11文件：**12文件 / 223 passed / 17.12s / 0 skipped**，`tsc --noEmit` exit0。与先前97项重叠不相加；保留此前普通运行PG证据，不重复无变化PG。此次UI兼容性差量独立审核结论另行追加。

`normal_runtime_final_review` 对精确 **`a8f895a7be267f03f084c18687b19895d56a1817`** 的入站生产UI差量、直接相关测试/合同及已有版本绑定审核记录独立核对，给出**合并兼容性PASS，0新增Critical/Important/Minor**。双方源码逐字保留、现HTTP/可信会话语义兼容，原容器P1仍关闭；已知UI P2与未完成真实平台/Windows/生产/客户验收继续保留。审核未重跑root测试，未重审200余证据文件；允许准确记录同范围QA/状态后正常推送，不批准未来接口或其他源码变化。root核对三份交接文档163个相对链接均有效，未解决冲突为0，文档差量格式检查通过。
