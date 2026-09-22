"""Pure human-evidence selection and projection; never modifies frozen raw facts."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import hashlib
from pilot.candidate_ingestion import _json
from pilot.candidate_review_contract import CandidateReviewError


def is_dynamic(raw):
    return (raw['kind'] == 'PAGE' and raw.get('normalizer_version') in {'dynamic-public-read-v1', 'dynamic-public-read-v2'}
        and raw.get('collector_version') == 'public-web-agent-v1')


def current_evidence(raw, verification, now):
    if not is_dynamic(raw) or not verification or verification['status'] != 'OPEN':
        return None
    checked = datetime.fromisoformat(verification['checkedAt'])
    if not timedelta(0) <= now - checked <= timedelta(hours=24):
        return None
    return verification if verification.get('demandEvidence') else None


def evidence_date(value):
    return datetime.fromisoformat(value['publishedDate']).replace(tzinfo=ZoneInfo('Asia/Shanghai'))


def validate_evidence(raw, value, status, now):
    if status != 'OPEN' or not is_dynamic(raw):
        raise CandidateReviewError('demand_evidence_unavailable',422)
    texts = [raw['content']['title'] or '', raw['content']['body']]
    if any(not any(value[key] in text for text in texts)
            for key in ('authorExcerpt','demandExcerpt','dateExcerpt')):
        raise CandidateReviewError('source_excerpt_mismatch',422)
    if not timedelta(0) <= now - evidence_date(value) <= timedelta(days=60):
        raise CandidateReviewError('source_expired',409)


def project_content(content, raw, verification):
    if not is_dynamic(raw):
        return content
    return content | dict(author_updates=[verification['demandEvidence']['demandExcerpt']] if verification else [],
        source_read_scope='HUMAN_CONFIRMED_EXCERPT' if verification else 'UNATTRIBUTED_PAGE')


def evidence_binding(raw, verification, now):
    if not is_dynamic(raw) or not verification:
        return {}
    return {'demandEvidenceBinding': dict(id=verification['id'],
        sha256=hashlib.sha256(_json(verification).encode()).hexdigest(),
        usable=current_evidence(raw,verification,now) is not None)}


def same_snapshot(current, snapshot):
    keys = ('binding','description','content','strategy')
    provenance = snapshot.get('sourceResearch',snapshot.get('research'))
    return (same_evidence(current,snapshot) and all(current[key]==snapshot[key] for key in keys)
        and (provenance is None or current.get('research')==provenance))


def snapshot_basis(snapshot):
    keys = ('binding','description','content','strategy','model')
    return {key:snapshot[key] for key in keys} | {
        key:snapshot[key] for key in ('demandEvidenceBinding','humanResearchAssessment') if key in snapshot}


def same_evidence(left, right):
    return left.get('demandEvidenceBinding') == right.get('demandEvidenceBinding')


def legacy_projection(value):
    if type(value) is dict:
        return {key:legacy_projection(item) for key,item in value.items()
            if key not in ('demandEvidence','demandEvidenceId')}
    if type(value) is list:
        return [legacy_projection(item) for item in value]
    return value
