# 原文来源连接失败的有界处理

用户已授权既定范围内自行细化并修阻塞；按验收优先约定串行在 main 实施，一次整批独立审核，不增加分支、重复构包或设计确认。

目标：某个公开来源 TCP 连接确定失败时记录一次失败读取，并允许研究其他已发现来源；不把来源不可达等同于无需求，也不重放同 URL。

设计：沿用已存在的确定 READ 失败合同，新增仅由 stdlib 读取器在 `socket.connect` 失败时产生的 `connection_unavailable`。连接阶段最多 5 秒且不超过当前读取期限的一半，给失败回执留出时间；总读取期限仍由父进程控制，不延长。DNS 私网、TLS/证书异常、发出 HTTP 后超时、父进程截止、401/403/429、ACK 丢失仍是原硬失败/UNKNOWN，不放宽代理、重定向、重试或原文验证。所有资源、状态与失败计数保留，只有实际成功读取才能入候选。

比较：单纯延长 20 秒会拖慢且不能解决不可达；无差别跳过 timeout 会掩盖已发请求未知；本方案只识别确定的请求前连接失败。

- [x] RED：worker 连接异常时未发送 HTTP、提前返回，send/TLS 错误不误分类；父进程、READ 合同、session/dispatcher 及事件解析保留新代码。
- [x] GREEN：修改 `pilot/open_web_reader_worker.py` 的连接阶段，贯通 `open_web_reader.py`、`public_read_session.py`、`responses_bridge.py`、`read_tool_client.py`、`research_effect_contract.py`、`codex_research_worker.py` 的固定失败代码。
- [x] 定向验证：上述 reader/contract/session/dispatcher 六文件 159 项通过；桥接三个相关用例通过（新增真实 loopback HTTP 链、同 URL 缓存与另一来源成功）。未使用 PG，不当成真实数据库全链证明。
- [x] 一次独立审核、代码 ba308e8 已提交 main。
- [ ] 部署前确认新旧读取合同/研究镜像版本并统一候选。真实客户端新业务任务还需单独证明，旧 UNKNOWN 不修改或重放。

本批证据：最初 4 项 RED，session/client 2 项 RED、纯事件解析 1 项 RED 后 GREEN。初次 POSIX worker 测试因本机缺可选 mcp 未收集，改为不依赖 POSIX/MCP 的纯事件测试；不把跳过写通过。review_connect_failure 发现 bridge 遗漏新码，真实 HTTP 链新增 RED 复现后补齐；最终差量独立 GO，无 P1/P2。bridge 整文件首次 43 通过/1 失败，失败是既有 oversized 本地 TCP 测试 WinError10053，未改该路径、未证明其旧版本结果；受影响 public-read 三项单独复核通过，不宣称全文件 GREEN。

服务器独立探针：在当时 customer 容器通过 stdin 加载本轮 worker（不写产品文件），对 www.v2ex.com 根页单次受控读返回 `connection_unavailable`/5.05 秒，未重放原客户任务、未用模型/搜索。该结果只证明当前读取器对连接失败的确定分类，不证明整轮研究成功。盘点发现 customer 已被并行登录发布更新为容器2474287、镜像2dd574b、revision标签unknown；ops与broker保持原ID，均健康。部署前需固定新源码，不能拿旧ff4ffec声明当前server版本或直接覆盖并行发布。

## 16:06 候选接续与并行来件

- 固定752aa24的customer候选 `sha256:0fcb676095a1527503e58e04f350660dd348ec654d640aebda1e6313e60f67cc`、research候选 `sha256:35cc1abec1963bb03710b26d560d628d209bb469a13c44e2de0f3ab2cdf5943d` 已构建；非root/只读/无网验证195个源码文件摘要及新读取合同通过。仅构建，未切换生产。初次依赖摘要差异确认仅CRLF/LF；脚本嵌套字符串转义错误修正后通过，未因此改变产品或依赖版本。
- Windows首次752aa24载荷通过118.40秒，构包前源码字节检查拒绝默认autocrlf检出；改独立LF检出且649项源码绑定通过。LF载荷通过124.46秒。随后main收到界面收敛a5183f0，独立差量review_trial_navigation GO、无P1/P2；尝试复用不变载荷被原同提交门禁拒绝，未放宽构包器。a5183f0新载荷通过114.51秒，真实Forge构包session93518已进入Squirrel制作，尚未确认完成或安装。旧产物保留，不重写摘要追认为新版。
- main又收到778e820三天试用自动开通及Login变更，已同步到5c142bb。因此正在制作的a5183f0包不是最终最新包，不能用它宣称最新登录验收。下一次候选只补该真实产品差量，不重复无关审核/全量测试；服务最终候选也必须包含145迁移和新的试用逻辑，不能将752aa24旧customer候选覆盖新生产。
- 只读部署准备确认配置/挂载保持原样、运行研究计数0、活跃研究容器0。最新线上customer已是容器bd8cfd1d、镜像be5d3c0a、revision778e820；旧研究broker仍71690b92/a91ea42。可用任务工具未返回Mac任务，未冒充已向Mac发送/收到ACK；通过main同步本记录。后续应统一研究协议发布与最终Windows包，避免并行反复切换同一服务。原未知任务仍保留且未重启。

## 16:23 同版部署与Windows实装

- 固定源码47eb746，customer镜像 `sha256:c91d0b30fb9e24153f86634696e6e0b39ef5578b512405457be3390d09d50fa0`、research镜像 `sha256:a85c06eb2d2ed9751698e376fbe5977e9b9cdb3b30421df1a096502579dc04b1`：实际构建及196项文件摘要/读取合同通过，包含145及三天试用。16:18真实切换完成，customer容器9c5c2c24、broker容器cc787039，公网readyz和本地readyz均200，broker私有socket连接通过；ops容器51a5e37a未变化。未改环境/挂载/端口/预算，旧镜像与ledger保留。
- 发布脚本 `.runtime/promote-research-47eb746.py` 先只读预检；review_release47指出并发覆盖、回滚准入和组件缺失恢复问题，合批修正后差量GO。发布共同锁 `/opt/yike-ai2026/ops/customer-research-release.lock` 与容器ID围栏同时使用；后续相关发布须遵循此锁。回退先停止pilot准入、确认无活动研究和容器；未知保留broker核对，外部容器变化拒绝覆盖。此次未触发回退，不将静态审核当真实回退演练。
- Windows a5183f0旧构包93518最终BUILT但未安装；当前47eb746载荷36804真实通过119.08秒，Forge95722 exit0，649项源码摘要构包前后相同 `7659879b31a9db02aeec50dc40855d43f42319e5bcb64f3c9953cd7ab56c557c`。安装包 `D:/ykf913/make/squirrel.windows/x64/YikeAI-Setup.exe`，SHA256 `3989107545016cb3278bbcf90b09b8a399c65b05a060f88c6e5ad63f5480ab0c`，NotSigned。
- 用户授权的测试会话草稿已放弃关闭，未删除正式任务/登录。首次安装35257 exit0实际因SQUIRREL_TEMP覆盖根目录安装到D:/ykfx913/YikeAI，不是原位置升级；日志与摘要定位后取消该覆盖，正常安装28659 exit0。原安装app.asar SHA256 `f758e67d2df8539ea471a265db1998d5dcfb14beb27b4141ac1627296e722e43` 与候选一致，实际原生窗口45810124启动、登录与已确认AI软件定制画像保留；正在从真实新建任务入口接续，不以实装和服务健康当研究成功。
- 为避免C盘空间不足，三份旧载荷portable-candidate-20260910-01-relocated、portable-https-7d3bfe7-relocated、portable-release-1119985-relocated从本仓库.runtime迁到 `D:/yk-retained-0913/`；文件数/总字节一致，未删除，当前构包输入未移动。后续main到b69a662只改官网/文档，desktop/pilot/app/migrations/skills/依赖差量为空，沿用47eb746实际产品字节，不重复构包。

## 16:29 最新客户端真实任务：模型过早结束，尚无原文

原生窗口45810124：创建“验收-AI定制新版研究-0913”，保留既有已确认AI软件定制/全国线上交付画像；真实建议返回10词，采用后选择公开网页自主研究。明确核对20来源/15分钟/20模型、100记录/900秒、10000搜贝上限，服务估算55搜贝；策略确认后创建，自动进入对应进度详情通过。首次本机原请求加载仍失败，单次只读刷新恢复；保留旧原请求、不重放。此启动体验缺口仍待修，不把人工刷新写成自动修复。

实际任务 `e90292be-5a0c-4c4d-846d-557174baf42f`，run `ed940590-14c0-4dca-86d6-7b98789c5310`，created16:29:12。点击开始研究后正常显示研究进行中；数据库唯一MODEL从08:29:39.827Z到08:29:45.044Z成功，08:29:50.754Z协调器STOPPED/no_verified_reads。没有SEARCH或READ、候选0，不能验证本批来源失败继续处理，也不能声称闭环通过。

只读检查该任务持久回执：两个真实工具均在请求中，tool_choice=auto、text.format.type=json_schema；模型直接返回research-citation-choice-v1，summary为“我需要先搜索AI软件定制开发的企业采购需求信息，再读取相关页面获取证据。”、pages=[]，没有function_call。**当前具体断点是模型把行动计划作为最终结果提前结束，不是本轮网络读取失败。** 下一批针对首次研究动作与最终输出阶段的执行约束做定向修复，保留原动作许可/账本/上限、取消与UNKNOWN、不重放此任务、不强制无关原文；随后复用统一候选流程验证。页面另有覆盖时间显示UTC且状态摘要陈旧的问题，待按主链影响合批处理，避免为每处文案重复构包。当前实际结果仍未满足邀请试用三关，Goal ACTIVE。
