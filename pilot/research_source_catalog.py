"""Closed research index catalog; never accepts caller supplied URLs."""
from dataclasses import dataclass
import hashlib
from uuid import UUID, uuid5

from pilot.execution_contract import ExecutionRuntimeError


@dataclass(frozen=True)
class ResearchSource:
    source_id: str
    endpoint: str
    input_sha: str
    sample_kind: str
    collector: str
    scope: str
    label: str
    version: int
    node: str | None = None


SOURCE_IDS = ('v2ex-latest-v1', 'v2ex-qna-v1', 'v2ex-outsourcing-authors-v1')


def research_source(source_id):
    if type(source_id) is not str or source_id not in SOURCE_IDS:
        raise ExecutionRuntimeError('invalid_request', 422)
    if source_id == SOURCE_IDS[0]:
        endpoint = 'https://www.v2ex.com/api/topics/latest.json'
        seed, kind, scope, label, version, node = ('v2ex-latest-index-v1',
            'LATEST_TOPIC_INDEX', 'V2EX_LATEST_INDEX', 'V2EX最新主题 · 公开单源研究', 1, None)
    else:
        node = 'qna' if source_id == SOURCE_IDS[1] else 'outsourcing'
        endpoint = 'https://www.v2ex.com/api/topics/show.json?node_name=' + node
        seed, kind, scope, version = 'v2ex-' + node + '-index-v1', node.upper() + '_TOPIC_INDEX', 'V2EX_' + node.upper() + '_INDEX', 2
        label = ('V2EX问与答 · 单源索引研究（未读评论）' if node == 'qna' else
                 'V2EX项目外包 · 单源索引研究（未读作者回复）')
    return ResearchSource(source_id, endpoint,
        hashlib.sha256((seed + '\0' + endpoint).encode()).hexdigest(),
        kind, source_id, scope, label, version, node)


def research_entry_hints() -> str:
    """Render advisory public entries from the closed source catalog."""
    entries = [f"- {source_id}: {public_url}" for source_id, public_url in
               zip(SOURCE_IDS, research_public_entry_urls(), strict=True)]
    return "\n".join((
        "## 仓库来源入口提示（仅供有权限的研究选择）",
        "仅在客户行业与技术社区匹配时考虑以下入口；这些示例不代表穷尽来源，也不授予页面读取或证据资格：",
        *entries,
        "latest/recent 最新主题混有广告和非买方内容，必须核对真实需求主体与行动信号。",
        "qna 是问题讨论，不得据此假定存在付费意愿。",
        "outsourcing 可含报价或项目需求，但必须核对作者身份、原文时间、当前状态和合作条款。",
        "节点页不同于标签页；不得把 tag/外包 与 go/outsourcing 的覆盖范围混为一谈。",
        "这些精确入口可直接读取；其他页面仍须由搜索结果或成功读页链接发现。猜测链接不获得权限。",
        "遇到登录要求、访问限制或风控时不得登录或重试，应如实记录覆盖缺口。",
    ))


def research_public_entry_urls() -> tuple[str, ...]:
    """Return the public HTML entry corresponding to each closed catalog source."""
    return tuple("https://www.v2ex.com/recent" if research_source(source_id).node is None else
                 "https://www.v2ex.com/go/" + research_source(source_id).node
                 for source_id in SOURCE_IDS)


def source_from_snapshot(snapshot):
    from pilot.research_runtime_config import public_research_snapshot
    if not public_research_snapshot(snapshot):
        raise ExecutionRuntimeError('strategy_conflict', 409)
    return research_source(snapshot['configuration']['publicSource'])


def planned_sources(snapshot):
    source = source_from_snapshot(snapshot)
    plan = snapshot['configuration']['research'].get('sourcePlan')
    return tuple(research_source(value) for value in plan['sources']) if plan else (source,)


def source_plan_action(task_id, run_id, source_id):
    research_source(source_id)
    return str(uuid5(UUID(run_id), 'research-source-plan-v1:' + task_id + ':' + source_id))


def source_record_limits(snapshot):
    sources = planned_sources(snapshot)
    total = snapshot['max_records']
    q, remainder = divmod(total, len(sources))
    return tuple(q + (index < remainder) for index in range(len(sources)))


def source_for_action(snapshot, task_id, run_id, action_id):
    sources = planned_sources(snapshot)
    if 'sourcePlan' not in snapshot['configuration']['research']:
        return sources[0]
    for source in sources:
        if source_plan_action(task_id, run_id, source.source_id) == action_id:
            return source
    raise ExecutionRuntimeError('request_conflict', 409)
