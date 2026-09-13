# 启动页任务记录短暂忙碌恢复

范围：用户既定自主推进及验收优先要求，串行main、一批定向验证及独立审核。只修启动页重复出现的任务记录首次加载失败，不改任务提交/取消/恢复或账号主进程的互斥保护。

证据：实装1549c18连续真实新任务都在确认页出现“本机原请求尚未读取成功”，手工只读刷新后恢复。代码deviceIdentityController.withAuthenticatedSession在设备准备或其它鉴权操作中返回BUSY，executionController将该结果原样交给LIST/RESEARCH_LIST。useDesktopExecution.refresh把一次BUSY立即视为读取失败，并且没有自动再读。未抓取本机真实IPC负载，因此BUSY是源码与可复现合同路径，不声称已记录每次实机失败的具体回执。

设计：仅LIST/RESEARCH_LIST收到明确BUSY时，按250/500/1000ms等待后再读，最多各4次。每次由原call校验当前账号scope及响应合同；账号切换/卸载后不再发送旧查询。FAILED、SIGNED_OUT、SESSION_CHANGED、网络异常、未知、超时等不自动重试；读不全仍阻止新建，不能假设空历史。START、CANCEL、RECOVER、RESEARCH_START、RESEARCH_RECOVER完全不使用该等待逻辑。选择局部读重试而不是删除鉴权互斥、假定空列表或跨页面重写队列。

- [x] 新增desktop/tests/ui/desktop-execution-list-busy.test.tsx：真实hook/合成服务回执，RED 3失败5通过；两类BUSY立即报错，持续BUSY只读1次。
- [x] desktop/src/renderer/pages/tasks/useDesktopExecution.ts增加私有列表调用，原状态/防重/普通变更通路不变。
- [x] 新用例10项与既有TaskWizard17项共27通过/3.97秒，typecheck通过；独立审核GO。与后续实际体验修复合批构一个新Windows候选，不逐行构包。
- [ ] 新候选构包/安装及首次读取的实机验证；当前运行的1549c18尚未包含本hook改动。

研究主线另有独立真实失败：90f58d1任务ce4f5bda-4290-4169-98e2-a9598e714e33于17:54:05从实装UI创建、17:54:28启动、17:55:02 STOPPED/no_verified_reads。4MODEL/2SEARCH成功，1次V2EX READ连接失败，0原文/候选。模型实际收到新增买方与来源切换指令（持久MODEL四次payload固定标记均存在），但两个实际查询仍偏AI品类，随后建议“后续补充其它来源”而提前结束；未证明改进效果。暂停同类盲测，不重复旧任务或升级为试用通过；下一步需针对工具返回与实际查询选择验证，原文/候选/草稿/反馈和三业务门禁仍未完成。

独立review_buyer_discovery本批GO，绑定hook blob `c66c53bc08ed8adb33fdf4afece2cb3bff3c1087`、test blob `07b8dfbc7d5eea0ea826b2e1511a454f2fb4364a`。等待计时器不主动取消，但在当前最多1秒等待后检查旧scope并退出；不会继续旧查询或把迟到状态写入新账号。本批不改变主进程鉴权，审核/测试不等于已实装。

客户端终态核查：研究区已显示暂停，但同页原采集状态仍待执行；进入“查看原文与分析”后实际待复核列表0条，没有生成草稿或反馈。保留状态不一致、覆盖面板过时/时区及技术说明冗余为同一个后续Windows体验批次，不以任务结束视为完成。下一轮研究诊断优先做一次“具体买方业务/寻源短语”和现有品类种子对照，保持同一真实画像、服务版本和预算；明确区分人工调整查询的诊断与客户只描述业务的自动体验，不能以人工挑选来源证明全自动达标。
