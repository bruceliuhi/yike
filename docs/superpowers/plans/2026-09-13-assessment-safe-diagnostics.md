# 判断失败的安全诊断与用量保留

目标：修复 ResearchAssessmentRunner 在 run_resource 吞掉异常后丢失适配器错误类别及已报告用量的问题。不改变UNKNOWN、防重、重试、扣量或客户API语义，不延长模型超时。

本批依既有范围内自主细化授权实施。最小方案：父进程为截止/退出/协议/进程IO给出固定内部类别；研究判断捕获适配器已知错误，只记录task/run/request/action UUID、固定错误类别、毫秒耗时和是否有测量用量。绝不记录异常正文、画像、来源文本、URL、密钥。日志不是权威计费或成功回执。

- [ ] 先写回归：原始provider-rejected/invalid-result/worker-deadline在仍然UNKNOWN时可区分；已知usage通过异常传至普通用量记录；无测量值保持null；错误注入文本不进入日志。
- [ ] 最小改动 candidate_assessment_model.py、research_assessment.py，测试 tests/test_assessment_safe_diagnostics.py。
- [ ] 定向RED/GREEN和既有模型/资源runner测试，独立审核具体提交；不重复模型调用、旧UNKNOWN、桌面构包或部署。

真实基线：4e4d3f7以前的a4d663e探针研究已完成但普通判断UNKNOWN；根本提供商/解析原因尚未证明。本批修复可观测性与用量丢失，不宣称旧UNKNOWN已恢复或新线索已成立。

## Evidence

Implementation pending.
