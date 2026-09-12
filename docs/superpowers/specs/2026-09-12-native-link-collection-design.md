# 原生内容／作者链接采集：分批接通

状态：范围内自主细化，按 AUTHORITY.md 的 2026-09-11 授权实施；不是生产启用。

## 目标与选择

用户应能选择多个平台、粘贴内容或作者主页链接，确认范围后执行有界采集，而不是只能反复换搜索词。现有界面可保存 links，但原生执行器只接受 search；XHS 的公开详情链接参数 xsec_token 还会被服务端通用敏感参数规则拒绝。

选择显式链接目标计划＋受控运行时逐平台接入。直接放开上游 detail/creator 会漏掉当前仅包在 search 上的账号校验；把链接转关键词则改变用户指定范围。二者均不采用。

## 第一批：可独立验收的输入边界

新增无网络、无浏览器副作用的双端链接解析与计划函数。识别以下 HTTPS 原生形式（可有末尾斜杠），不跟随短链接：

| 平台 | 内容 | 作者 |
| --- | --- | --- |
| B站 | www.bilibili.com/video/BV＋10位字母数字 | space.bilibili.com/正整数 |
| 抖音 | www.douyin.com/video/正整数 | www.douyin.com/user/ASCII字母数字下划线短横线 |
| 小红书 | www.xiaohongshu.com/explore/24位小写十六进制 | www.xiaohongshu.com/user/profile/同形式ID |
| 知乎 | www.zhihu.com/question/正整数/answer/正整数；zhuanlan.zhihu.com/p/正整数；www.zhihu.com/p/正整数；www.zhihu.com/zvideo/正整数 | www.zhihu.com/people/ASCII slug |

数字 ID 1–20 位且非零开头；作者 slug 1–128 位。知乎文章统一 canonical_url 为 zhuanlan.zhihu.com；答案 external_id 为 answer:ID、文章 article:ID、视频 zvideo:ID。其他 external_id 为路径 ID。输出固定四字段 platform、kind（detail/creator）、external_id、canonical_url。原始完整输入仍保留在确认快照，不被静默替换。

拒绝 HTTP、凭据、端口、未知主机／路由、片段、路径编码或点段、反斜杠、空白／控制字符、畸形百分号、重复查询参数、登录秘密参数。原始 scheme／host 只接受表中精确小写，不通过 URL 自动归一化接受编码主机或默认端口。查询参数必须含等号，键解码后只允许 ASCII 字母数字、下划线、点、短横线；按小写键判重。查询解码采用 UTF-8 严格解码及标准加号转空格，再拒绝空白、反斜杠和 Unicode 控制／格式字符。任意含 token/cookie/session/authorization/signature/password/secret 的键拒绝，以下公开 XHS 参数例外；modal_id 拒绝，避免把作者页浮层中的视频误认为作者范围。

仅原生 XHS 路由允许精确小写键 xsec_token（1–1024 位 base64url/base64 字符）及 xsec_source（1–80 位字母数字下划线短横线），两者同时存在或同时不存在；canonical_url 保留这两个参数并按固定顺序编码，其余跟踪参数丢弃。没有公开令牌只表示能识别链接，不表示页面可访问。不得因此放宽候选证据 URL、Cookie 或私密信息规则。

计划输入为已选平台数组与链接数组，1–4 个互异原生平台、1–100 个链接；每条必须属于已选平台，每个已选平台必须有目标；按 platform＋kind＋external_id 拒绝同目标的不同跟踪／令牌链接，避免重复执行。保持用户输入顺序。纯链接新任务 PREPARE（source=links、research=null）双端执行该校验；历史快照读取与哈希不改写，研究链接和关键词任务沿用旧规则。XHS 签名公开链接在配置校验处使用精确原生解析例外，不开放任意 token。

第一批不增加 capability、不变更执行策略、部署环境或上游 patch；旧运行时仍拒绝 links。验收只证明有效输入可以形成一致计划、无效范围在新任务准备前失败，不证明采集完成。

## 后续批次的执行要求

1. 主进程、Python host、source driver 传固定模式与目标字段；不用 URL 假装关键词，不通过 shell 或任意参数运行。完整快照绑定和全任务预算不变。
2. 详情目标只读指定内容及有界评论；作者目标只读该作者有界近期内容及评论，不读无关私人资料，不声称遍历所有历史。账号校验须包住实际 detail/creator 入口与请求；风控／身份变化立即停止，不能吞异常变成无数据。
3. 每个平台受控 patch 必须补齐结构校验、进度、终态、数量／时间上限、父内容关联与严格输出前缀；上游删掉的路径需按当前治理重建，不能直接恢复全部代码。更新 lock 与安装摘要，复用固定上游版本。
4. 原生链接能力通过新的显式支持声明分阶段启用；旧部署、未安装对应运行时不得报告支持。once/monitor 复用同样范围校验；不借机扩展 research 或公共网站任意抓取。
5. 完成当前代码的受控链路后，再用获授权 Windows 与平台账户验真实内容、取消、账号变化和候选回读；无 Windows 时不得升级为平台已验收。

独立审核按整批进行，定向测试覆盖变更，既有固定邀请安装包不随每个源代码提交重复构包。其他真实缺口（普通判断用量、增量游标、作者变化事件、多源研究）仍在完整 V0.2 范围，不以本批关闭。
