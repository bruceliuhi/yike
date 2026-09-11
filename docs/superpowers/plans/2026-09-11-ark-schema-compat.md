# 火山方舟最小结构化输出兼容

主线接收：`b18ed127f504ee303ad8dfd1f8fc1b551fc6cb6d` 经非作者独立整批GO，主工作区快进后新增13项差量通过并已推main。未部署该源码或配置模型；用户追加要求评估最新已开通型号，旧Flash实测仅为兼容证据，不作为最终默认选择。

用户要求复用本地火山方舟用于意客；主线程负责唯一生产写入，本侧仅在隔离分支修改模型请求并交主线程独立审核。

## 范围与实现步骤

- [x] 用两个产品 adapter 的原样请求复现方舟拒绝字符串 `maxLength`、数组 `maxItems`。
- [x] 在 `tests/test_ark_schema.py` 固定 RED：仅精确 HTTPS `ark.cn-beijing.volces.com/api/v3` 处理 schema 节点的字符串 minLength/maxLength、数组 minItems/maxItems；保留同名 properties、其它 provider、原 schema 和本地约束。
- [x] `pilot/provider_schema.py` 提供 `provider_json_schema(schema, *, base_url)`，复制 schema；仅将对应四约束移至该节点 description（要求模型遵守），不改变 required/enum/结构/引用/其它约束。
- [x] 候选分析和搜索建议仅在构造 response_format 时调用该函数。不新增重试、宽松 JSON、超时或凭据自动复用。
- [x] 定向运行 `pytest -q tests/test_ark_schema.py tests/test_search_suggestion_model.py tests/test_candidate_assessment_model.py`；记录原失败、真实合成调用与独立审核，再交主线程集成。

不改 schema 原生成器及本地 Pydantic、逐字引用、长度/数量、防冲突和完整响应校验；不读取客户资料、不真实采集、不外联。资料提取与短句教练原本使用 json_object，本片不改。

## 部署配置（不含秘密）

在客户服务私有 env 显式配置以下两组各自的 BASE_URL/API_KEY/MODEL，不能隐式继承另一组：

- `YIKE_PILOT_ASSESSMENT_*`
- `YIKE_PILOT_SEARCH_SUGGESTION_*`

BASE_URL 为 `https://ark.cn-beijing.volces.com/api/v3`；两路 MODEL 最终选择 `doubao-seed-2-1-turbo-260628`（以下最新选型取代初始 Flash 探测选择）；API_KEY 从用户批准的本地 ARK_API_KEY 安全注入，不能写本文或客户端。启用模型不自动批准资料外发、平台采集、联系或搜贝收费。

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

## 用户截图模型选型更新（2026-09-11）

用户批准比较截图已开通模型并直接使用。主线程已独立审核并集成 schema 补丁 b18ed12；本节另行交主线程审核，不与 schema 集成或线上启用混同。

- 官方目录把旧 Seed 1.6 / Flash 250615 标为即将下线，不作为新生产默认。
- Seedance、Seedream 为视频/图片生成，不能承担本片的文本结构化分析。DeepSeek V4 Pro 本次未做付费比较，不宣称质量低于选中模型。
- 三款各执行搜索建议、合成采购需求判断一次，默认深度思考均在当前30秒边界超时，不能只替换 MODEL 上线。
- 同样请求仅加入官方 `thinking: {type: disabled}`，仍用产品原严格解析：

| 模型 | 搜索秒 / 总 tokens | 采购判断秒 / 总 tokens | 官方输入/输出元每百万 tokens |
| --- | --- | --- | --- |
| doubao-seed-evolving | 16.8 / 1906 | 19.1 / 6527 | 6 / 30 |
| doubao-seed-2-1-pro-260628 | 15.9 / 1818 | 22.6 / 6696 | 6 / 30 |
| doubao-seed-2-1-turbo-260628 | 13.4 / 1929 | 18.3 / 6551 | 3 / 15 |

- 选择固定版 Turbo：此轮正确保留采购信号，同时将未核验入口判 UNKNOWN/REVIEW，不擅自可发；价低且响应更快。样本很小，不是稳定性能或全行业准确率结论。
- Turbo 追加两条合成反例：供应商广告 EXCLUDE / SUPPLY_OR_JOB（20.4秒）；仅“学习了，收藏一下”的评论即使父帖采购预算5万元仍为 OBSERVE / LOW intent（17.3秒）。两条均通过原引用等校验，不实际联系。
- `bounded_generation_options` 只对精确方舟北京 HTTPS endpoint + 精确选中 Turbo ID 返回 disabled；搜索、采购判断、资料提取、短句教练四个单次结构化请求使用。不影响其他模型/供应商或 Agent 推理策略，不加重试，不延长截止，不减弱验证。
- 新增四 adapter × 三种配置测试先 RED 4 failed / 8 passed；实现后定向五套 **400 passed**，一条既有恶意输入序列化警告。无全仓测试/重复构包。
- 最终产品路径真实合成调用：搜索9.5秒/1752 tokens；采购判断15.9秒/6415 tokens；资料提取3.3秒，均通过现有解析。资料和采购判断走原受控子进程。
- 短句首次4.6秒只通过 adapter JSON 解析，正文没有问号且 question 不在 content，**不计业务通过**。补充两种短句提示的精确包含及买卖角色要求，不放宽业务校验；新增提示回归 RED 后通过，定向短句9 passed / 1数据库测试未运行。修正后真实子进程3.7秒，同时通过原 `build_suggestion`：`您提到有200份产品手册要建知识库，想了解你们的手册格式？`。未发送。
- 已观察到搜索建议可将“不接招聘”泛化为排除招聘系统开发，仍须走现有用户确认，不把模型建议自动当成真实画像或完整行业策略。这里只证明接入可用，非所有行业准确率。
- 此追加补丁与最终模型配置须由主线程独立审核并统一部署；本侧没有写生产。上线状态应以主线程部署记录为准。
- 模型调用发生于授权账号，仅用合成业务文字。密钥不存代码、日志、文档或客户端。超时请求是否产生费用以供应商账单为准；未把模拟传输当真实调用。

依据：[官方模型列表](https://docs.volcengine.com/docs/82379/1330310?lang=zh)、[Evolving说明](https://docs.volcengine.com/docs/82379/2549861?lang=zh)、[官方价格](https://docs.volcengine.com/docs/82379/1544106?lang=zh)。三页均于2026-09-11查阅；Evolving固定ID自动更新，生产本片不启用该漂移别名。
