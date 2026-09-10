# Win 确认执行候选 · 2026-09-10

源码：`1a47178a129c07be9895de309fa121f3cf261a45`；独立审核绑定树 `81b47489abd2764502eb59a35c516dd8e0a15a78`，SPEC 后架构/代码/质量 PASS，无未关闭发现。

## 本批交付与验证

- 既有确认按钮接入主进程固定 START/CANCEL/LIST/RECOVER；身份和设备取主进程，原请求先落盘，列表失败禁新建，未知结果保留原 UUID，重试/取消分别人工确认。
- 定向：主控制器最初两文件 141 项通过，补严格输出后执行控制器 27 项通过；renderer 新增 22 项、旧任务/策略 45 项通过；根最终 DOM/shared/main/preload 35 项通过。集合重叠，不累加。类型检查通过。
- 真实 HTTP/受限 PostgreSQL：`tests/test_desktop_execution_http_postgres.py` 最终 **1 passed / 0 skipped / 3.24s**。普通 identity/controller 经产品传输，磁盘重建恢复丢失 START 回执，换会话拒旧签名，取消后数据库仅一任务四操作；临时专属容器已移除。预绑定设备、来源能力和保护适配为测试夹具。
- 浏览器隔离 TEST：实际准备/确认策略→原按钮启动 UNKNOWN→查询原 UUID 得 PENDING→明确取消得 CANCELED；按钮防重与整页布局已检查。最终历史文案和中文标题为差量更新，DOM 验证通过；没有重复整链或全套测试。
- 审核发现的最终 epoch 窗口、输出私有字段透传均有 RED→GREEN；独立仅复跑两条针对性反例。历史启动回执明确不代表当前任务状态。

## 范围限制与接续

Windows 候选：`desktop/out/candidate-1a47178/YikeAI-Setup.exe`。410 个 desktop 输入构包前后匹配源码；一次 make、结构校验、实际 main/preload/renderer 严格 smoke（含固定执行 IPC 的未配置服务状态）通过，实际 ASAR 25 个脚本/页面未含本批 TEST 夹具。Setup SHA256 `571dd76d08f41b138db8e6786fc6dfde837c41b6760ca2af498772ad73fe771c`；ASAR `6fe6cfb201fa715c3d73ae951778794fee8ca03544bc6fe3f09ea77f02b7ad86`。NotSigned；未执行安装/卸载。旧 `e5774b6` 候选保留，不冒充本包。

新执行入口仅支持无研究计费的单次任务；研究用量、监控调度、真实来源/runtime 门禁保留。默认运行时仍 NOT_READY，不能把设备 READY、测试场景或安装包当作真实采集成功。真实平台/收发、安装卸载及客户 UAT 尚未完成，05F 和完整 Goal 保持 IN_PROGRESS。

Win 接续真实来源 worker、原文候选与联系跟进闭环；Mac 保留后端执行/回复及其在途修复，不重复桌面文件。仅通过 main 交接，不代写 Mac ACK。构包版本及文件摘要见本批候选说明；纯文档来件 `64c90c5` 不触发重测或重构。
