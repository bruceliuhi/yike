# 自主研究首次动作约束

用户已授权范围内自行细化开发，按验收优先串行main、一批定向验证和一次独立审核，不另起确认或重复构包。

真实前提：47eb746客户端任务e90292be只完成一次MODEL，两个工具均存在但tool_choice=auto，模型把“需要先搜索”作为json_schema最终结果返回。没有SEARCH/READ；旧任务不重放。

目标：已确认自主研究的首次请求须选择已允许的搜索或读页工具，不只返回计划；后续可正常完成、报告无结果或访问失败。保持调用/来源/时间预算与账本、取消及未知边界。

设计：ResponsesBridge增加内部布尔require_initial_tool，默认false；仅受控且绑定研究上下文的worker启用。首次实际准入MODEL设置tool_choice=required并由原账本持久化同一payload；其余请求原样，未暴露任何有效工具时拒绝而非直接转发。保持终稿schema，不添加补发循环、不调用隐式搜索。相比加强提示词更明确；相比每轮强制工具不会阻止合法结束或强制无关读页。供应商是否遵循须真实验证，不能由合成测试代替。

- [x] tests/test_research_first_action.py：真实loopback桥接配合合成供应商，先RED（新参数不存在，5失败/1通过），实现后验证首required、后续auto、schema/业务不变、预算不扩和默认兼容。
- [x] pilot/responses_bridge.py及pilot/codex_research_worker.py最小实现，定向pytest与必要worker接线检查。
- [ ] 独立整批审核、提交main；按产品差量统一候选，真实客户端新任务验证搜索→原文，不回写旧失败。

当前不因本批重做已有回收/安装测试；初次本机请求读取与覆盖时区显示作为同一交付批次的已知体验缺口保留。

验证：首次动作+effect合同50通过；接入真实effect_input/effect_result校验后，Windows桥接相关12通过/5.62秒。隔离Linux镜像无网络、只读根、非root、无客户/密钥挂载，首次动作与worker有/无编译上下文的实际入口9通过/2.85秒；provider和工具结果是合成，worker执行为真实子进程，不等于供应商实网。首次Linux测试仅因测试辅助py.py缺失未能启动，补齐离线测试依赖后通过，没有修改产品依赖。主干6423c43官网来件已快进整合，不影响本批产品字节。

独立整批审核review_first_action：基线6423c432，四文件差量可提交，无P1/P2；仅代码放行。effect合同44项追加检查通过/0.43秒。尚未部署、构包或实网验证本修复，完整Goal继续。
