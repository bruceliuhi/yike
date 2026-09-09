# V02-02A 来源 origin 规范化更正

> For agentic workers: use test-driven-development and independent requesting-code-review; do not modify the Mac working branch.

**Goal:** 修复 Win 对 `e4d1695749f037bcafa13f77e703544b67b25c09` 交叉审核发现的来源身份错误，不改变上传/鉴权范围。

**Evidence:** Python 内建 IDNA2003 将 `faß.example` 合并到 `fass.example`，而当前 Node WHATWG URL / HTTP 客户端将其解析为不同 origin。PUBLIC_WEB 相同站内 ID 因此错误冲突。相反，等价压缩/展开 IPv6 未规范化，造成同一来源生成不同身份。

**Architecture:** URL 校验与来源 origin 继续共用一个 host 规范化函数。IP 字面量使用标准 ipaddress 的规范表示，保留全部现有特殊用途/私网拒绝。域名使用已锁定的 `idna==3.18`，明确 UTS46 非过渡映射和严格域名校验，不使用 IDNA2003。将现有传递依赖提升为直接依赖，锁定节点版本及摘要不变。保留百分号主机拒绝、单尾点、Unicode 等价点、敏感 query、控制字符等安全边界；不发起 DNS 或请求网络，不改原 public_url 内容快照。

## 实施与验收

1. 在 detached 更正快照先加公开入口和 source_identity 的真实反例：ß/ss 是不同来源、Unicode/A-label 是同一来源、展开/压缩 IPv6 是同一来源；取得 RED。
2. 最小修改 `pilot/candidate_contract.py`、对应测试；显式依赖只改 `pyproject.toml` 与 `uv.lock` 根项目依赖/metadata，禁止无关升级。补非法 A-label/域名、Unicode 点和私网 IPv6回归，拒绝时保持稳定错误码且不暴露原文。
3. 技术契约明确新规则。运行候选/来源、旧纯解析器、研究导入相关回归；`uv lock --check`、compileall、diff check通过。当前已安装 idna 3.18 可用于定向验证，无需 editable 安装。
4. 非实现者独立复审精确更正快照；根代理保留 e4 原始182通过与漏测问题，补充新测试结果和接收范围后正常集成main。仅 DTO/纯函数可获得限定 ACK，不代表 HTTP 上传、设备执行授权或真实采集。

文件边界：以上两代码/测试文件、pyproject/uv.lock、`docs/contracts/V02_CANDIDATE_INGESTION.md`。计划与最终QA/任务书由根代理维护。不得改迁移、身份、UI或 Windows runtime 文件。
