# 本机资料、任务返回与回复入口：可见验收

2026-09-10。产品与Mac包候选 **8af8eafba0faef68ae48ea76f3d5d4a70c7b06c8**；本次主线 **d5ee8c27532ff15436eaa2bcfeafca1a9e0e86a0** 的 desktop 树与其相同。保持批准的R3/R4规范；本批主要补日常交互、原生操作和指定状态布局证据，不宣称全部页面状态、后台接入或商业上线完成。

## 结果与范围

| 内容 | 实际结果 |
|---|---|
| P04本机资料 | 保存画像后原稿仍可用；带入只预填，取消不写，人工保存后同步表出现草稿且原稿保留。该操作链在前一fca构建实际执行；8af仅压缩空同步列表的大块空态。新8af首屏1280×720显示整行及三个操作，带入按钮y495.8/h36，无文档横溢。 |
| P06任务返回 | 实际从第二步“查看范围”到平台连接，切设备与使用授权，再顶部返回；仍为`/tasks/new?step=connect`，任务草稿未启动。 |
| P09监控返回 | 知乎离线→检查设备→返回保留同任务、平台状态标签及知乎；小红书失效→重新连接→取消，直接回同任务/同标签/小红书。未执行平台登录或任务。 |
| P14/P15独立回复 | 初始人工列表为空；选择商机仍可查看匹配回复；标已读不增加人工行，未匹配回复仍独立且未读；按该目标添加先取消再保存，目标保留，切“全部”才显示唯一人工事实。全部是隔离TEST内存，未收到或发送真实消息。 |
| Mac当前包 | 冷启动、输入、取消关闭继续编辑、保存75搜贝会话草稿、明确放弃关闭、进程退出、同目录重启及清空后的新任务均实际操作。用户已同意Windows手工验收；本批不代签Windows。 |

## 原生生命周期

CUA按完整路径选择 `desktop/out/visible-local-8af8eaf/意客AI.app`，避免多个同bundle ID旧包误认：

1. 原旧包15583正常退出后，最新包冷启动为41032；[画面](screenshots/native-cold-start-8af8eaf.jpg)是完整窗口，1080×768像素。[初始AX](native-cold-start.txt)仅增量diff，不是完整树。
2. 新建任务输入`TEST 原生验收 8af8eaf`。首次paste工具返回剪贴板读取超时，但随后AX已显示文本，未重复粘贴。Cmd+Q出现[真实提示](native-unsaved-prompt.txt)与[260×162原生对话框截图](screenshots/native-unsaved-prompt-8af8eaf.jpg)。
3. 点击“继续编辑”，名称仍在；输入75搜贝并点击保存。[保存后AX](native-saved-session-draft.txt)显示本机会话草稿、未启动。
4. 再Cmd+Q，明确点击“放弃更改并关闭”；CUA返回App quit，读取进程确认41032已退出。
5. 同路径重新打开为44236，见[工作台](native-restarted-workbench.txt)与[新建空任务](native-restarted-empty-task.txt)。这是提示中明确约定的退出清除会话草稿行为，**不是退出后持久保存**。随后返回工作台。

[进程与ASAR摘要](native-process-binding.json)记录上述观察；独立审核另用ps及lsof核对44236实际打开同目录ASAR、旧进程已不存在。摘要布尔值不是完整原始命令日志。真实文件选择/保存框未在这条链中执行，包内smoke的对话框替身不算原生选择器验收。

## 浏览器状态与证据

IAB/CUA运行18794静态TEST构建，复用真实App/页面/路由，完整[资源清单](test-preview-build.json)绑定8af。P04修复前两张JPEG绑定先前fca已加载页面；重新加载后才捕获新8af compact图，不能用当前资源清单追认旧截图。

- P04同1280×720状态：[修复前](screenshots/p04-local-drafts-1280x720.jpg)、[修复后](screenshots/p04-local-drafts-compact-1280x720.jpg)、[当时预填抽屉](screenshots/p04-transfer-drawer-1280x720.jpg)、[新DOM测量](p04-compact-layout.json)。前后图独立实看通过；没有批准图中完全相同的local-drafts状态，因此只签收这个布局改善，不写全P04设计PASS。
- P06：[第二步](p06-step-connect.txt)、[设备页返回参数](p06-settings-route.json)、[返回步骤](p06-returned-step.txt)、[最终路由](p06-return-route.json)。
- P09：[离开前](p09-before-settings.txt)、[设置参数](p09-settings-route.json)、[设备返回](p09-after-settings.txt)、[返回路由](p09-return-route.json)、[连接弹窗](p09-connection-dialog.txt)、[取消后](p09-after-connection-cancel.txt)、[同平台路由](p09-after-connection-cancel-route.json)。取消弹窗直接回监控页，因此后续尝试点设备页签无匹配；据新DOM停止，没有把工具超时当产品缺陷。一次goto返回ERR_ABORTED、旧页仍在；随后用新TEST标签完成P06，不把这次直接导航计为成功。
- P14：[空人工+未匹配](p14-unmatched-empty-manual.txt)、[空人工+匹配](p14-matched-empty-manual.txt)、[标已读](p14-matched-read.txt)、[未匹配仍未读](p14-unmatched-after-read.txt)、[添加取消仍保留目标](p14-add-cancel-retained.txt)、[首次人工保存](p14-first-manual-saved.txt)。保存后“待跟进”不列已回复且未设下次时间的事实；切“全部”能看到唯一记录，不误写保存后默认列表立即新增。

首次高层截图存在缩放/裁切与CSS尺寸失配，独立复核发现后不予通过，保留[校准记录](capture-calibration/README.md)。原生及P04初始截图实际为JPEG，已原字节改正后缀；P06/P14三张早期图片实际1024×576，不作为1280验收。后续最终CDP截图不裁切、不改页面样式，在尺寸切换后用后续独立观察核对稳定CSS及实际PNG大小；浏览器仿真不替代Windows缩放。

## 构包、测试和独立审核

[342项输入](final-build-inputs.json)与Git/隔离构建目录逐项相同。8af的[33项针对性测试](logs/yike-material-empty-compact-tests.log)、[类型](logs/final-typecheck.log)、[Mac构包](logs/final-mac-build.log)、[严格smoke](logs/final-packaged-smoke.log)、[生产排除](logs/final-production-exclusion.log)通过。此前桌面全量1340 passed/23 skipped绑定d816，详情及初次失败见[前批](../ui-local-handoff/README.md)，不冒称在8af重跑全量，不累加测试数量。

[实际包绑定](final-mac-package.json)：ASAR `98debe8e3c1e58e93e3da04209abc38d7773909ff4a3fb5ff317e7068c9fd067`；ZIP `f580c225264db5cd23f9033e235ecf2f35e3a9e1fd3e682e19f78647033d8569`，ZIP内ASAR相同。产物为`desktop/out/visible-local-8af8eaf/意客AI-darwin-arm64-0.2.0.zip`，未提交二进制。

[独立产物核对](reviews/yike-visible-local-evidence-review.md)与[P04独立视觉复核](reviews/yike-visible-p04-layout-review.md)分别限定通过；报告早先提到的png后缀已修正，历史审核原文保留。后端来件[限定兼容复核](../ui-local-handoff/reviews/yike-local-handoff-incoming-2d799bc.md)不冒认真实触达/回复服务接通。旧804测试尝试实际是文件未找到/no tests，保留[失败日志](../ui-local-handoff/logs/incoming-804dece-reply-tests.log)；本次d5精确四个reply/outreach文件实际[32 passed/0.14s](logs/incoming-d5ee8c2-reply-outreach-tests.log)，不追认旧失败或算作真实PG。

05A与完整Goal保持进行中。真实服务按原负责人接续，保留原生选择器、未覆盖页面状态、Windows安装/缩放/卸载与生产部署未验项。四个untracked raw候选草稿没有纳入代码、测试或产品能力。

## P11当前Mac交互观察

在`?scenario=P11&state=populated&suite=r4`实际读取CAPTURED快照，展开/收起长正文，打开版本明细，切到项目变化。见[初始详情](p11-captured-collapsed.txt)、[长文展开](p11-expanded.txt)、[版本明细](p11-version-detail.txt)、[项目变化](p11-project-changes.txt)。四类时间、原帖/父评论的上下文标签和逐字引用分别展示，切标签后快照仍在。该合成夹具的机会头部为展区公开网站，而快照为门店评论，用于不同组件状态覆盖，不能当一致真实业务案例或对外演示数据；本批只记录有限交互兼容，不把它当R4同状态整页视觉通过。

## 跟进页尺寸核对

最终[P14尺寸与PNG绑定](p14-final-responsive.json)覆盖1280×720、1366×768、1440×1024、1920×1080、2560×1440。同一“全部/已有一条明确人工登记/匹配回复已读”状态；仅此状态，没有覆盖全页所有状态或Windows系统缩放。第一次2560虽PNG头正确但画面裁切，已另存校准目录；重新取图后再做独立视觉判断，不以PNG头单独放行。

最终[独立五尺寸复审](reviews/yike-visible-p14-final-review.md)限定PASS：前四张保持原图，2560新图SHA `0d119999091e0556876ce62e7033076a415b56acf43413f09780c530c25e3913`已单张实际复看，侧栏208px、页头与两栏及操作完整。已清除每页CDP模拟与浏览器viewport覆盖；未改变生产页面样式或保留调试模拟。

P11主线程已把[当前1484×1060实图](screenshots/p11-captured-collapsed-1484x1060.png)和批准R4-05-P11图同一输入实看：侧栏、字色、两栏、原文折叠及右侧准备操作无明显破版；批准图是公开样例的“多找类似”抽屉，当前是客户TEST详情，状态不同，故不把这对图冒称同状态完整设计比对。后续正式业务演示应使用一致来源的合成或授权真实数据。

归档时仅去掉三份构包/定向日志的行末空格与末尾空行，不改执行内容、结果或失败记录。

## 并发主线接收：62e7a1c

先提交本批QA为b95d753，再普通合并已审83e76be形成 **62e7a1c5e4fc76155b2208fbdcbf5961f53c1f1f**，无冲突、无强推。来件新增候选纯协议及测试尚未装配，原运行入口未变，8af包保留原输入/运行图绑定，不声称新HEAD完整源码树等于旧包清单。独立[限定来件复核](reviews/yike-visible-incoming-83e76be.md)保留P07和真实回复未接通边界。

root在62e实际执行候选/旧页面/客户端四套[80 passed](logs/incoming-83e-desktop-tests.log)、[类型检查](logs/incoming-83e-typecheck.log)及reply两套[20 passed](logs/incoming-83e-reply-tests.log)。这是纯接收集合，无PG，不重复全桌面/构包或用来件受限PG结果代替本轮回复SQL实写。

[最终归档文档独立审核](reviews/yike-visible-final-doc-review.md)有限PASS：51个当时本地引用、五张最终PNG/CSS/SHA及测试归属通过；审核绑定其明确时点，不回填为合并后全源码测试。

## 最后来件改变了运行路径：bd4b86a

普通推送再次因另一端先推进而拒绝，未强推。正常合入9a59288后为 **bd4b86a846a3703b9954a6c81e633a81ec1d11b4**。此次包含Win候选固定传输/真实读取接线60b2523，确实改变desktop生产运行图，与前段83e独立协议不同。当前P07只启用真实读取；旧页面隐式复核保持禁止，完整人工核验/写入恢复归其后续任务，不伪称全链完成。

root在bd4实际[9文件198 passed/2.49s](logs/incoming-9a-desktop-tests.log)，tsc退出0，见[精确验证](incoming-9a-validation.json)。本批Mac包/可见TEST仍绑定8af，不能宣称它们已经验过此后新接线；仓库main与冻结安装产物分开交付。当前新增候选服务的实际HTTP/PG、全P07及后续发行由原负责人接续，本片没有代签。

9a接收另完成[当前生产renderer构建与TEST排除](logs/incoming-9a-renderer-exclusion.log)：4778模块、0个harness manifest引用、failures为空。该命令显式检查的ASAR仍是8af旧包，不把existingAsarChecked=true冒称新接线Mac构包。

最后[候选读取接线独立接收](reviews/yike-visible-incoming-9a59288.md)限定PASS：双方源码完整，P04/P06/P09/P14文件未覆盖，nullable来源与原请求范围保护保留。此后58219d4仅追加执行PG验证文档，正常保留，不借来件测试扩大本片结论。
