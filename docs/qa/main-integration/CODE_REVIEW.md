# 主线整合独立代码审核

日期：2026-09-09。审核者：独立代码 Agent `design_handoff_code`。

审核对象为冻结提交 **`cd642bddfc1238853a21a7aef39a2c0432dbe38a`**，比较基线为本轮获取的 `origin/main` 提交 `e7c94a9`。结论只绑定此候选及下述范围；之后有业务修改或并发合并，需按增量复核。

**结论：本次审核范围未发现新增 P0/P1；可作为产品主线整合提交合并到 `yike-ai2026/main`。** 这是代码集成准入，不是完整付费版、Windows 实机或生产上线准入。审核期间未修改产品代码、未执行平台采集或消息发送。

## 独立性与范围

- 审核 A 的采集组件源码打包与安装增量：`scripts/package_mediacrawler.sh`、`scripts/fetch_mediacrawler.sh`、`tests/test_vendor_packaging.py` 及相应说明。
- 审核 B 的研究包事务与查询字段移植：`pilot/store.py`、`pilot/research_import.py`、`tests/test_import_atomicity.py`；核对当前租户 provision、RLS、画像确认和 UI facade 的边界未被旧分支覆盖。
- 审核 B 的 `desktop/tests/visual/` 和 `desktop/vite.visual.config.ts`：生产入口排除、测试数据标识、存储与外部动作隔离，以及组件测试的实际覆盖。
- 审核主 Agent 的仓库工作流、AUTHORITY、任务书、整合台账和双 AI 历史文档范围声明。

本 Agent 编写的 Windows 六文件**不纳入自审结论**：`desktop/scripts/build-windows.ps1`、`desktop/scripts/windows-build-evidence.mjs`、`desktop/tests/windowsBuildEvidence.test.mjs`、`desktop/docs/WINDOWS_ACCEPTANCE_TEMPLATE.md`、`desktop/docs/PACKAGING.md`、`docs/qa/ui-r3/windows-evidence-writer-check.json`。它们需要其他 Agent 的独立审核。

## 代码结论

1. **源码包保留固定提交与许可证，输出不覆盖已有文件。** [打包器](../../../scripts/package_mediacrawler.sh)第 23–43 行检查现有输出、干净且固定的 checkout，以及当前树和可达历史中的受限路径；第 54–80 行只在临时独立 bare 仓库建立引用，按 manifest、bundle 的顺序排他发布完整文件。异常清理仅针对本次发布的 inode，没有写入或删除源仓库引用。[安装入口](../../../scripts/fetch_mediacrawler.sh)第 41–79 行对 bundle、锁文件、补丁集合、固定提交和许可证逐项核对。
2. **受信研究包改为真正的整包数据库事务。** [研究包入口](../../../pilot/research_import.py)第 14–74 行仍先校验全部证据，再调用 PostgreSQL 批量入口；[存储层](../../../pilot/store.py)第 117–124 行在同一 connection context 中执行全部条目，异常会使前面写入的来源、版本、观察和商机一并回滚。第 130–153 行保留服务端租户解析、画像行锁与已确认版本要求，并补齐同一导入键的公开 URL 冲突检查。单条兼容入口也走相同内部实现，没有新增客户端管理员导入 API。
3. **查询补字段没有扩大租户可见范围。** 商机列表的来源 JOIN 和最新跟进子查询均显式匹配 `tenant_id`；详情继续使用原租户过滤。新增字段未修改响应之外的管理员配置、数据库连接、会话、Origin 或 RLS 规则。移植限于受信研究包和查询修复，未带入旧 Jinja 页面、旧演示启动器或旧产品范围。
4. **视觉工具独立于产品入口。** Forge 仍使用原 `vite.renderer.config.ts`；生产 `src/` 未导入视觉目录。测试入口仅监听固定 loopback 端口，无业务 proxy；用每实例内存数据和 TEST 标识运行真实 App/Page。浏览器存储改为内存，native bridge、业务 fetch/XHR/beacon、外链、剪贴板和下载均被拦截；任务启动、候选入库及消息发送始终拒绝。生产排除脚本检查真实构建模块图、manifest、产物文本及存在的 ASAR，缺少 ASAR 时不会伪报包检查完成。
5. **文档冲突按最新授权收敛。** 产品代码归 `yike-ai2026/main`、新功能分支按 `codex/` 建立；`yike-ai` 的只读过渡与后续迁移安排清楚。双 AI 任务板及计划保留历史内容，但已在顶部明确 DISCOVERY/SQLite/双平台限制不覆盖当前 V0.2、多平台、PostgreSQL、R3 和客户端目标。整包事务可以列为完成的子能力，任务总体仍为 `IN_PROGRESS`。

## 验证证据与边界

本审核者在冻结前对相同待提交实现独立执行了：

- `npm test -- tests/visual`：2 个文件、15 项通过，覆盖真实页面组件、内存实例隔离、外部动作拦截和任务/发送拒绝。
- `.venv/bin/python -m pytest tests/test_vendor_packaging.py -q`：13 项通过，包含真实本地 Git bundle 往返、许可证摘要、已有文件/符号链接保护、源引用保留和历史环境文件拒绝。
- `bash -n scripts/package_mediacrawler.sh`：通过。

冻结后已核对上述实现与候选一致，并只读审查真实 PostgreSQL 测试：它要求管理员和非超级用户、非 BYPASSRLS 应用角色指向同一隔离库；覆盖后条目冲突回滚四类表、同键 URL 冲突、重复导入和跨租户查询。主 Agent 报告同树桌面 238 项、相关 Python/vendor/隔离 PostgreSQL 共 95 项通过，以及类型、秘密扫描、Shell、编译和差异检查通过。本审核未重复运行整套测试，也不将其他 Agent 的执行记录写为本人重新执行。

保留以下交付限制：

- 源码包验证使用本地 fixture，没有打包真实上游授权源码或完成平台安装/采集。路径筛查不等于内容级秘密扫描；实际分发仍须核查授权源码及可达历史。
- 整包事务覆盖当前 PostgreSQL `PilotStore`；无批量接口的离线验证 adapter 仍保留逐条协议，不能扩展解释为任意实现都有原子性。
- 视觉 harness 的合成运行/跟进状态仅用于界面评审。20 个入口存在不代表全部状态已视觉验收；内存 Storage 的键枚举与真实浏览器存储也不完全等价，后续若用该工具验收“清空尚未读取的种子草稿”需补保真测试。
- 原生导出保存桥、真实连接器、执行器、正常客户登录、触达及回复等尚未完成的能力，不因合并主线变成可用。尤其不能把浏览器下载触发或页面提示作为 Electron 文件实际落盘的证据。
- Windows 构建/安装/缩放、正式签名分发以及 CP-06 生产部署验收仍是独立门禁；本结论不批准对外发送、收费承诺或生产上线。

## 并行主线文档合并增量复核

增量对象：**`cd642bddfc1238853a21a7aef39a2c0432dbe38a` → `238172f396638132f2cff93a5c07318a5717beba`**。仅 `docs/DUAL_AGENT_TASKBOARD.md`、`docs/INTEGRATION_STATUS.md` 和双 AI 协作计划发生变化；`pilot/`、`desktop/`、`scripts/`、`tests/`、`migrations/` 与已审候选完全一致，本次未重跑代码测试。

**增量结论：PASS，无新增 P0/P1；原代码准入及交付限制继承。** 合并保留并行主线 `6f449e6` 的 V0.2 修正，将协作建议明确置于唯一实施任务书之下；不重置已完成工作或 Mac 前端 Goal，保留 `pilot/`、`desktop/` 作为实际入口以及用户手动 Windows 验收方式。触达规则明确为“未经人工确认不发送”，未缩回永久禁用发送。

非阻断 P2：协作计划第 34、43、52 行的 `Files` 仍指向旧 `app/`、`static/`/`app/web/`，第 39 行还保留“后端检查全部通过才进入 UI/触达依赖”的宽泛门禁。顶部已规定当前入口和前端独立推进，故未形成新的执行授权或产品代码回退，但正文与顶部不一致会增加后续 AI 误选目录、冻结前端的概率。建议将三处目录与 `pilot/`、`desktop/` 对齐，旧目录注明仅作复用来源，并将门禁限定为依赖新 API 的实际联调。

### 文档增量最终复核：P2 已闭环

最终绑定提交：**`386e8e28c0c9360af168d536c5dd86545535e0e9`**。本结论覆盖 `cd642bdd` 至该提交的全部文档增量，包含 `238172f` 的并行主线合并。

已逐行核对最后四处修正：Task 2、3、4 的实现目录统一为 `pilot/`、`desktop/` 及相应测试目录；旧 `app/`/适配器明确仅作经评估的复用来源。后端验收依赖仅约束使用新 API 的实际联调，已授权前端按现有契约继续。上一节 P2 因而关闭；主整合记录也已准确保留 `6f449e6` 的 V0.2 修正。

**最终增量 PASS，无新增 P0/P1，未遗留本次文档合并阻断。** 产品源码与已审 `cd642bdd` 一致，未重跑代码测试；原独立性排除、main 代码集成准入以及 Windows、真实平台与生产交付限制均继续有效。
