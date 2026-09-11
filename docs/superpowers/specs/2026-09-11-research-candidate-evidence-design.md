# 研究原文进入现有候选库

V0.2内自主细化，承接已批准的研究执行路线。目标是让一次受控公开读取的合格原文在现有候选列表/详情可读，恢复时不重读、不重入库；不代表意向研究、模型效果或全网搜索已完成。

选择复用现有candidate sources/versions/observations/projections/batches。另建研究结果库会复制复核/详情流程；把研究伪装成普通CLAIM则会伪造lease事实，均不采用。仅抽取原入库循环为共享内部事务函数，旧签名上传与授权不变。

新内部ResearchCandidateStore连接资源许可与候选持久化。执行器成功回调把已校验结果交给内部提交方法，在一个PG事务内写原文/观察/回执、增加任务记录计数、终结原SOURCE_READ事件；提交失败不返回原文成功，原动作保持ISSUED，恢复只读已有回执。不新增HTTP消费接口，不放开普通research CLAIM/upload。

研究批次使用明确的research-resource-v1执行上下文，绑定原task/run/platform_run、设备、reservation/action/permit、research_generation=1及输入/输出摘要。没有lease_id或普通execution_generation。新增数据库延迟约束把批次绑定同用户、同任务且SUCCEEDED的资源事件；现有原文详情解析增加此严格分型，现有人工复核与来源证据保留不变。

固定V2EX索引是未判断原始样本。标题/正文超界、空正文或非法记录不截断、不补造，记录未纳入数；候选记录上限与SOURCE_READ次数分开。返回observed_count、accepted_count、skipped_invalid_count、skipped_budget_count，四者核算一致。原帖发布时间与采集时间保留；不附加买方身份、预算或购买意图。

已发出的读取即使随后取消/撤权，仍可登记事实和原文；登记不产生新许可或继续执行授权，后续人工/模型决策沿现有当前资格校验。会话失效拒绝新登记。服务端受信入口独立于客户端，数据仍按tenant/owner隔离。

验证：新受限PG链路、回滚/跨账号/不同动作去重、终态冲突、记录上限；旧入库定向回归；客户端新旧上下文及拒绝伪造绑定；一次非作者整批审核。读取使用合成响应完成大部分验证，最多一次真实固定公开读取并核对现有详情，不发送外部消息。无默认研究启动/规则/模型/生产启用，不关闭完整Goal。
