"""Closed research index catalog; never accepts caller supplied URLs."""
from dataclasses import dataclass
import hashlib

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


def source_from_snapshot(snapshot):
    from pilot.research_runtime_config import public_research_snapshot
    if not public_research_snapshot(snapshot):
        raise ExecutionRuntimeError('strategy_conflict', 409)
    return research_source(snapshot['configuration']['publicSource'])
