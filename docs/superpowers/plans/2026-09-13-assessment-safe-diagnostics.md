# 判断失败的安全诊断与用量保留

目标：修复 ResearchAssessmentRunner 在 run_resource 吞掉异常后丢失适配器错误类别及已报告用量的问题。不改变UNKNOWN、防重、重试、扣量或客户API语义，不延长模型超时。

本批依既有范围内自主细化授权实施。最小方案：父进程为截止/退出/协议/进程IO给出固定内部类别；研究判断捕获适配器已知错误，只记录task/run/request/action UUID、固定错误类别、毫秒耗时和是否有测量用量。绝不记录异常正文、画像、来源文本、URL、密钥。日志不是权威计费或成功回执。

- [x] 先写回归：原始provider-rejected/invalid-result/worker-deadline在仍然UNKNOWN时可区分；已知usage通过异常传至普通用量记录；无测量值保持null；错误注入文本不进入日志。
- [x] 最小改动 candidate_assessment_model.py、research_assessment.py，测试 tests/test_assessment_safe_diagnostics.py。
- [x] 定向RED/GREEN和既有模型/资源runner测试，独立审核具体提交；不重复模型调用、旧UNKNOWN、桌面构包或部署。

真实基线：4e4d3f7以前的a4d663e探针研究已完成但普通判断UNKNOWN；根本提供商/解析原因尚未证明。本批修复可观测性与用量丢失，不宣称旧UNKNOWN已恢复或新线索已成立。

## Evidence

代码`bd64b0f9aeb1c5a88b4e5647381cf03e4eb9398d`。初始4项RED；修复后新测试、既有模型与资源runner213项通过4.60s。增加父进程真实退出/截止/畸形输出及模型返回后校验失败的用量保留测试，初始1失败7通过；修正合成输入投影并保留已返回的有效usage后8通过0.50s。既有测试不重复构包或整库运行。

独立`assessment_diagnostics_review`在同SHA给出Spec PASS / Quality PASS，无P0/P1/P2，独立41项通过，另以实际run_resource及合成资源store验证usage/null、重放不重试和worker_io。审核简报`/tmp/yike-assessment-diagnostics-review.md`。未进行新PG、生产、模型或真实平台调用；旧UNKNOWN底层原因仍未知。

研究日志事件`research_assessment_failure`只含关联UUID、固定model_error、固定diagnostic或null、elapsed_ms与usage_reported布尔值。子进程已知错误通过既有安全code区别；父进程worker_deadline仅表示宿主截止，不推断远端是否完成或提供商是否超时。run_resource.finish回执丢失等无已捕获适配器错误路径没有被本批证明可诊断，未知继续占用、不重试。下轮用新任务观察准确故障，不重放旧UNKNOWN，也不拿本地代码修复宣称商业闭环完成。
