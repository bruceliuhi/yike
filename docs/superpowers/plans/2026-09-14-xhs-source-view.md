# 小红书原文查看 Implementation Plan

> 按用户已批准的范围内自主细化要求执行；使用 subagent-driven-development 分离导航与主进程接线，最终一次批次审核。main 小改串行提交，未完成接线不得称用户可用。

**Goal:** 客户从真实候选点击原文时复用本机当前账号的平台会话，定位同一原帖，不再仅把无参数链接交给未登录的系统浏览器。

**Architecture:** 原文证据仍保留无凭据canonical URL。主进程按当前用户/设备读取候选当前版本及其观察，解析同源 note ID、原查询和已知原帖作者；profile由既有加密store提供，renderer不提供路径或Cookie。受监督的只读浏览器会话复用既有profile锁及退出处理；只点击源站实际可见的精确同ID链接，临时URL参数仅在浏览器内存中。打开不写核验声明、不发送、不自动将候选入库。

**Tech Stack:** TypeScript/Electron existing identity/profile/IPC，Python existing governed Playwright runtime，Vitest/pytest targeted checks。

## 取舍与边界

- 不采用恢复含访问参数的云端候选URL：现有证据合同禁止且会扩大敏感信息流转。
- 不采用重新要求用户在系统Chrome登录作为产品默认方案：与已批准的授权持久化体验不一致，且裸URL仍未证明可访问。
- 采用同会话平台内定位：已知POST作者可复用已存在的作者主页真实链接导航；COMMENT作者不是原帖作者，不借用。未知原帖作者可使用该候选保存的原查询在平台搜索，再点击精确同一note ID的实际链接；不得打开相似内容替代。
- 所有导航前后核对官方origin、当前账号及取消状态。输入必须严格限制note ID、可选作者ID和有界查询；不把输入当selector片段或脚本。不处理验证码、不导出Cookie、不绕过源站限制。
- 仅匹配唯一可见链接；核对跳转后的原帖ID，并检查实际详情存在，404/错误/缺失不得报成功。若精确链接不在首屏，返回不可定位，不进行无界滚动或扩大采集。
- COMMENT若仅打开所属原帖，明确提示“已打开所属原帖，未定位该评论”，不称评论原文已重开，不写评论核验成功；不因此扩大为评论深采。
- 新查看入口的生命周期必须覆盖用户关闭、超时、切换账号、退出应用和profile繁忙；未知清理不伪造成功。窗口可用与来源真实性/联系权限分开。

## Chunk 1：同会话只读定位

- [x] 新建 app/xhs_source_navigation.py（可测试、无CLI、无profile读取、无Cookie/API取数/文件输出）：接收现有page及严格目标，核对账号，打开官方主页/作者页，通过页面搜索框或实际作者页链接定位唯一相同note ID；失败为固定无原始数据错误。可选query只用于原始搜索动作，明确不是换词找相似。
- [x] 新建 tests/test_xhs_source_navigation.py：先RED；合成页面覆盖同ID、带临时参数实际链接、错ID、重复/隐藏链接、未知作者查询、错误页、账号变化、取消、输入非法和原始参数不出结果。再最小实现与GREEN；仅本文件及必要现有导航测试。

## Chunk 2：客户端接线与实机

- [x] 新建 desktop/src/main/xhsSourceTarget.ts 及 desktop/tests/xhsSourceTarget.test.ts：复用现有严格rawEvidence解析，用renderer当前版本绑定比对服务端当前证据；只从精确current_observation取原查询与连接，不借其它历史记录。COMMENT作者不作为原帖作者；源URL/ID需完全匹配固定规范，参数不进入目标。先RED再实现。
- [ ] 基于既有受监督host/driver增加只读查看生命周期，不复用发送上下文、不把AUTHENTICATED当原文已打开。主进程获取当前候选与profile绑定，仅传当前账号目标；新IPC由受信renderer触发；已有系统浏览器入口保留其它平台/公共网站行为。
- [ ] 原文按钮接入当前candidate ID/version，打开中禁重复，结果以简单中文显示；不写来源核验、不发起发送。账户切换/退出停止会话并释放profile锁。
- [ ] 定向验证身份/目标绑定、旧版本拒绝、busy/失败/cleanup、UI接线；独立批次审核后合并构一次最新Windows候选，真实用户路径验证同条原帖可读，未通过则保留失败继续修复。

此计划不缩小发布目标：三业务任务、有效买方线索、草稿反馈及真实用户认可仍需完成；原文导航单元测试不等于平台实机成功。

## 本轮基础模块验证（未接线、未构包）

目标投影：首次缺模块无法加载，增加拒绝占位后有效RED 3失败/6通过，实现后9通过；补sourceKind区分POST/COMMENT时有效RED 2失败/7通过，最终仍9项通过（不累计重复运行）。typecheck通过。

导航：50项初始RED后50通过；检查发现泛匹配“验证码/404”会误伤正文，另以5项RED驱动修正为内容区外的精确平台提示，同时加入实际“当前笔记暂时无法浏览”提示；随后页面就绪等待新增2项RED，修复后最终66通过/13.71秒（不累计重复运行）。全部离线页面替身，未访问真实平台。候选搜索框input#search-input尚未实机验证，缺失即返回固定失败。此刻真实客户端仍638906e，不含新查看入口。

基础模块独立Spec/Quality审核GO，无P1/P2；绑定导航blob `f81e3e76ef2c206bd9b8597b3ec488031516df80`、Python测试 `62ea58634019b6409de679ce1b61cad68965e9fc`、目标解析 `b97a29b5ecb2d627af5e79484c12cdf3506b9b2b`、TS测试 `27dca827f9a01016faebc95ebe6ef8248c17811f`。该结论仅覆盖基础模块，不代表host/driver/IPC/UI或实机可读性完成；复用同字节测试证据，不重复构包。

下一接线位置已确认：main.ts attachPlatformRuntime内复用profileStore与runtime配置，identity.requestApi({operation:'candidates.rawEvidence',payload:{candidateId}})取当前证据，现有resolveCollectionAccount校验当前连接/profile。查看器须把scope当前性/AbortSignal贯穿异步步骤，并加入before-quit的停止链。不得调用outreach执行或伪造其上下文。renderer Opportunities.openSource 当前仍只有service.openExternal，需新增只读IPC后才替换小红书分支。接线及真实源站验证是必做后续，不因本轮单元测试通过而认为修复完成。
