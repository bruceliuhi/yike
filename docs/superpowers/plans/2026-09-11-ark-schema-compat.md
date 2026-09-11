# 火山方舟最小结构化输出兼容

用户要求复用本地火山方舟用于意客；主线程负责唯一生产写入，本侧仅在隔离分支修改模型请求并交主线程独立审核。

## 范围与实现步骤

- [x] 用两个产品 adapter 的原样请求复现方舟拒绝字符串 `maxLength`、数组 `maxItems`。
- [x] 在 `tests/test_ark_schema.py` 固定 RED：仅精确 HTTPS `ark.cn-beijing.volces.com/api/v3` 处理 schema 节点的字符串 minLength/maxLength、数组 minItems/maxItems；保留同名 properties、其它 provider、原 schema 和本地约束。
- [x] `pilot/provider_schema.py` 提供 `provider_json_schema(schema, *, base_url)`，复制 schema；仅将对应四约束移至该节点 description（要求模型遵守），不改变 required/enum/结构/引用/其它约束。
- [x] 候选分析和搜索建议仅在构造 response_format 时调用该函数。不新增重试、宽松 JSON、超时或凭据自动复用。
- [ ] 定向运行 `pytest -q tests/test_ark_schema.py tests/test_search_suggestion_model.py tests/test_candidate_assessment_model.py`；记录原失败、真实合成调用与独立审核，再交主线程集成。

不改 schema 原生成器及本地 Pydantic、逐字引用、长度/数量、防冲突和完整响应校验；不读取客户资料、不真实采集、不外联。资料提取与短句教练原本使用 json_object，本片不改。

## 部署配置（不含秘密）

在客户服务私有 env 显式配置以下两组各自的 BASE_URL/API_KEY/MODEL，不能隐式继承另一组：

- `YIKE_PILOT_ASSESSMENT_*`
- `YIKE_PILOT_SEARCH_SUGGESTION_*`

BASE_URL 为 `https://ark.cn-beijing.volces.com/api/v3`；MODEL 初始选择已经过合成探测的 `doubao-seed-1-6-flash-250615`；API_KEY 从用户批准的本地 ARK_API_KEY 安全注入，不能写本文或客户端。启用模型不自动批准资料外发、平台采集、联系或搜贝收费。

## 初始证据与边界

- 基线 d59ae1f 两套：366 passed / 1 failed。既有 `test_default_transport_disables_retries` 断言旧 content()，而 envelope 已返回含 strategy 的 adapter_content()；仅更正这处预期，不改运行逻辑。
- 原样产品请求两路 provider_rejected；简单 json_schema 请求200，证明凭据至少可用于该请求，不证明所有模型权限或余额。
- 仅裁剪四项后，搜索返回 intentSignals=[] 被本地拒绝；标准模型 assessment 30秒请求超时。均不记为成功。
- 把裁剪限制保留为 description 后，Flash 两路真实合成探测通过原产品解析：搜索3.0秒/1999 tokens；候选6.0秒/7051 tokens。合成业务输入不是真实线索或行业效果证明。
- 实际产品补丁、独立审核和生产配置尚待后续验证。不得把此处探测结果升级成已经部署。

## 补丁验证

- 新增测试初次 RED 11 failed / 2 passed；实现后加固坏结果断言为确切本地校验错误码，避免把传输失败误计为严格校验成功。
- 定向三套 **380 passed / 1既有恶意输入序列化警告**；`git diff --check`通过。没有运行全仓、数据库或重复构包。
- 实际补丁两条公开产品 adapter 再次调用真实方舟、合成输入、严格输出解析通过：Flash搜索 **2.8秒 / 1828 tokens**，候选 **3.9秒 / 6420 tokens**。候选走原受控子进程，不是用临时宽松HTTP代替产品路径；无真实客户资料。
- 以上是候选代码及真实模型兼容性证据，不证明稳定准确率、线索质量或已部署。主线程尚须独立审核本批后统一配置生产，不由本侧更改服务器。
