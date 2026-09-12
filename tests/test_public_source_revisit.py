"""Synthetic bounded source revisits; never evidence of real platform reading."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from pilot.candidate_contract import validate_candidate_batch, batch_fingerprint, CandidateContractError
from pilot.execution_contract import ExecutionOperation, ExecutionRuntimeError
from tests.test_execution_api import operation_payload, auth_headers
from tests.test_public_sampling_progress import _support_client
from tests.test_public_sampling_progress import (
    sampling_databases, _sampling_env, _begin_sampling_claim, _authenticated_https_client,
    _sign_apply,
)
from tests.test_candidate_ingestion_postgres import payload, submit
from pilot.candidate_ingestion import CandidateIngestionStore
from tests.test_monitor_runtime_postgres import runtime_pulse

SOURCE = 'v2ex-outsourcing-authors-v1'


def page(topic):
    return dict(kind='PAGE', external_source_id=topic, external_comment_id=None,
                public_url=f'https://www.v2ex.com/t/{topic}', title='合成需求',
                author_public_id='7', body='企业软件合成需求', published_at=None,
                observed_at='2026-01-01T00:00:00Z', parent=None, collector_version=SOURCE,
                normalizer_version='v2ex-author-page-v1', query='企业软件',
                source_context=dict(schema_version='v2ex-author-context-v1', replies_expected=0,
                    replies_read=0, replies_complete=True, supplements_read=False, author_replies=[]))


def result(request, topic='101', outcome='READ'):
    return dict(schema_version='public-source-revisit-v1', claim_request_id=request['request_id'],
                topic_id=topic, outcome=outcome)


def finish(env, begun, lease, value):
    _sign_apply(env, dict(schema_version='execution-runtime-v1', request_id=str(uuid4()),
        operation='FINISH', device_id=env.device, credential_version=1,
        task_id=begun['task_id'], platform_run_id=lease['platform_run_id'],
        lease_id=lease['lease_id'], execution_generation=lease['execution_generation'],
        upload_request_id=value['request_id']))
    env.monitor.pulse(env.claims, runtime_pulse(env, monitor_session_id=str(uuid4())))


def test_real_pg_revisit_lru_commit_validation_replay_and_https(sampling_databases, tmp_path):
    import copy
    import json
    import os
    from pathlib import Path
    from tests.test_device_keys import encoded
    env = _sampling_env(sampling_databases, source=SOURCE)
    store = CandidateIngestionStore(env.db, env.execution)
    session, events = str(uuid4()), []
    with _authenticated_https_client(env, tmp_path) as client:
        for number in range(6):
            begun, request, lease = _begin_sampling_claim(env, session, client=client, version=2)
            events.append(dict(kind='execution', request=request, receipt=lease))
            sampling = lease['public_sampling']
            assert sampling['schema_version'] == 'public-sampling-round-v2'
            assert sampling['round'] == number
            expected = None if number % 2 == 0 else {'topic_id': '101' if number in (1, 5) else '102', 'query': '企业软件'}
            assert sampling['revisit'] == expected
            value = payload(env, begun, lease, records=[page('101'), page('102')] if number == 0 else [])
            if expected:
                value['public_revisit'] = result(request, expected['topic_id'], 'UNAVAILABLE' if number == 3 else 'READ')
                if number != 3:
                    value['records'] = [page(expected['topic_id']) | {'body': '已经找到团队了'}]
                bad_values = []
                missing = copy.deepcopy(value); missing.pop('public_revisit'); bad_values.append(missing)
                for field in ('lease_id', 'run_id'):
                    bad = copy.deepcopy(value); bad.pop('public_revisit')
                    bad['execution'][field] = str(uuid4()); bad_values.append(bad)
                for changes in ({'claim_request_id': str(uuid4())}, {'topic_id': '999'}):
                    bad = copy.deepcopy(value); bad['public_revisit'].update(changes); bad_values.append(bad)
                if number != 3:
                    for changes in ({'query': 'wrong'}, {'collector_version': 'wrong'},
                                    {'public_url': 'https://example.com/t/101'}, {'source_context': None}):
                        bad = copy.deepcopy(value); bad['records'][0].update(changes)
                        if changes == {'source_context': None}: bad['records'][0].pop('source_context')
                        bad_values.append(bad)
                else:
                    bad = copy.deepcopy(value); bad['records'] = [page(expected['topic_id'])]; bad_values.append(bad)
                for bad in bad_values:
                    with pytest.raises((ExecutionRuntimeError, CandidateContractError), match='public_revisit_conflict|INVALID'):
                        store.prepare_signing_payload(env.claims, bad)
                    with pytest.raises((ExecutionRuntimeError, CandidateContractError), match='public_revisit_conflict|INVALID|lease_conflict|execution_conflict'):
                        submit(env, store, bad)
                assert _sign_apply(env, request) == lease
            else:
                with pytest.raises(ExecutionRuntimeError, match='public_revisit_conflict'):
                    submit(env, store, value | {'public_revisit': result(request)})
            response = client.post('/api/ui/candidate-submission-signing-payload', json={'batch': value})
            assert response.status_code == 200, response.text
            prepared = response.json()
            signature = encoded(env.key.sign(prepared['signing_payload'].encode()).signature)
            response = client.post('/api/ui/candidate-batches', json={'batch': value, 'signature': signature})
            assert response.status_code == 200, response.text
            receipt = response.json()
            assert receipt.get('public_revisit') == value.get('public_revisit')
            assert submit(env, store, value) == receipt
            assert _sign_apply(env, request) == lease
            events.append(dict(kind='candidate', request=value,
                               prepared={'batch_fingerprint': prepared['batch_fingerprint']}, receipt=receipt))
            finish(env, begun, lease, value)
    artifact = os.environ.get('YIKE_PUBLIC_REVISIT_HTTP_ARTIFACT')
    if artifact:
        Path(artifact).write_text(json.dumps({'events': events}, ensure_ascii=False, indent=2) + '\n')


def test_claim_v2_and_support_negotiate_explicitly():
    body = operation_payload('CLAIM') | {'public_sampling_version': 2}
    assert ExecutionOperation.model_validate(body).model_dump(mode='json') == body
    client, _ = _support_client()
    response = client.get('/api/ui/execution-support?sampling_version=2', headers=auth_headers())
    assert response.status_code == 200
    assert response.json()['public_sampling'] == 'committed-round-revisit-v2'


def test_public_result_dto_is_strict():
    from pilot.public_source_revisit import PublicSourceRevisit
    value = {'schema_version': 'public-source-revisit-v1', 'claim_request_id': str(uuid4()),
             'topic_id': '101', 'outcome': 'READ'}
    assert PublicSourceRevisit.model_validate(value).model_dump(mode='json') == value
    for changes in ({'topic_id': '01'}, {'topic_id': '١'}, {'topic_id': '9007199254740992'},
                    {'topic_id': True}, {'outcome': 'DELETED'}, {'claim_request_id': 'bad'},
                    {'unknown': 1}):
        with pytest.raises((ValidationError, ValueError)):
            PublicSourceRevisit.model_validate(value | changes)


def test_v2_nonclaim_and_native_combination_rejected():
    for operation in ('START', 'RENEW', 'CANCEL'):
        with pytest.raises((ValidationError, ExecutionRuntimeError)):
            ExecutionOperation.model_validate(operation_payload(operation) | {'public_sampling_version': 2})
    with pytest.raises((ValidationError, ExecutionRuntimeError)):
        ExecutionOperation.model_validate(operation_payload('CLAIM') | {
            'public_sampling_version': 2, 'native_progress_version': 1})


def test_candidate_result_legacy_absence_and_strict_platform():
    from tests.test_candidate_contract import batch, NOW
    legacy = validate_candidate_batch(batch(), now=NOW)
    assert 'public_revisit' not in legacy.model_dump(mode='json')
    with pytest.raises(CandidateContractError):
        validate_candidate_batch(batch(public_revisit=result({'request_id': str(uuid4())})), now=NOW)
    value = batch(platform='PUBLIC_WEB', records=[])
    value['execution'].update(access_mode='PUBLIC_ANONYMOUS', connection_id=None, connection_version=None)
    plain = validate_candidate_batch(value, now=NOW)
    revisit = validate_candidate_batch(value | {'public_revisit': result({'request_id': str(uuid4())})}, now=NOW)
    assert batch_fingerprint(plain) != batch_fingerprint(revisit)
    with pytest.raises(CandidateContractError):
        validate_candidate_batch(value | {'public_revisit': None}, now=NOW)


@pytest.mark.parametrize('source,round_number', [(SOURCE, 0), (SOURCE, 2), ('v2ex-qna-v1', 1), ('v2ex-latest-v1', 1)])
def test_no_revisit_for_even_rounds_or_other_public_sources(source, round_number):
    from pilot.public_sampling_progress import committed_public_sampling_round
    class Cursor:
        def __init__(self):
            self.rows = iter([(str(uuid4()), {'configuration': {'mode': 'monitor', 'publicSource': source}}),
                              (round_number,)])
        def execute(self, *_): pass
        def fetchone(self): return next(self.rows)
    progress = committed_public_sampling_round(Cursor(), tenant_id='tenant', owner_user_id='user',
        task={'task_id': 'task', 'profile_version_id': 'profile', 'strategy_version_id': 'strategy'},
        platform={'platform': 'PUBLIC_WEB', 'access_mode': 'PUBLIC_ANONYMOUS',
                  'platform_run_id': 'platform-run', 'run_id': 'run'}, version=2)
    assert progress['round'] == round_number and progress['revisit'] is None


def test_v2_empty_or_invalid_history_and_scope_isolation(sampling_databases):
    base = _sampling_env(sampling_databases, source=SOURCE)
    for env in (_sampling_env(sampling_databases, tenant=base.tenant, source=SOURCE),
                _sampling_env(sampling_databases, tenant=base.tenant, user=base.user,
                              profile=base.profile, source=SOURCE)):
        begun, request, lease = _begin_sampling_claim(env, str(uuid4()), version=2)
        assert lease['public_sampling']['revisit'] is None
        value = payload(env, begun, lease, records=[page('101')])
        submit(env, CandidateIngestionStore(env.db, env.execution), value)
        finish(env, begun, lease, value)
    begun, _, lease = _begin_sampling_claim(base, str(uuid4()), version=2)
    value = payload(base, begun, lease, records=[page('201') | {'query': 'wrong'},
        page('202') | {'public_url': 'https://other.example/t/202'},
        page('203') | {'collector_version': 'wrong'}])
    submit(base, CandidateIngestionStore(base.db, base.execution), value)
    finish(base, begun, lease, value)
    _, _, second = _begin_sampling_claim(base, str(uuid4()), version=2)
    assert second['public_sampling']['round'] == 1
    assert second['public_sampling']['revisit'] is None
