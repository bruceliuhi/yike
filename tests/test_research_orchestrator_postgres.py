"""Actual confirmed task → raw inbox → metered review; synthetic I/O only."""
from datetime import UTC, datetime

from pilot.candidate_review import CandidateReviewStore
from pilot.research_candidates import ResearchCandidateStore
from pilot.research_orchestrator import ResearchOrchestrator
from tests.test_candidate_assessment_model import CONTENT
from tests.test_candidate_review_postgres import (BoundaryModel, databases, env,
    execution_databases, execution_env, raw_databases, raw_env)
from tests.test_confirmed_strategy_review_postgres import real_strategy_env
from tests.test_research_candidates_postgres import topic
from tests.test_research_resources_postgres import started, store


def test_confirmed_research_sequence_persists_assessments_and_recovers_once(real_strategy_env):
    from pilot.research_assessment import ResearchAssessmentRunner
    env = real_strategy_env
    execution, _ = started(env)
    resources = store(env)
    class Model(BoundaryModel):
        def assess_before(self, deadline, **kwargs):
            assert deadline > datetime.now(UTC)
            return self.assess(**kwargs)
    model = Model()
    reviews = CandidateReviewStore(env.db, model=model, strategy_resolver=env.strategies.resolve,
        strategy_snapshot_reader=env.strategies.read_snapshot,
        research_assessment=ResearchAssessmentRunner(resources))
    sequence = ResearchOrchestrator(ResearchCandidateStore(resources), reviews)
    reads = []
    def fetch(_deadline):
        reads.append('read')
        return [topic(i, title=CONTENT['title'], content=CONTENT['body']) for i in (251, 252)]
    scope = dict(task_id=execution['task_id'], run_id=execution['run_id'])
    first = sequence.run(env.claims, **scope, fetcher=fetch)
    assert first['phase'] == 'ANALYZED'
    assert first['accepted_originals'] == first['analyzed_originals'] == 2
    assert model.calls == 2 and reads == ['read']
    assert first['sending_authorized'] is False
    for item in first['review_results']:
        assert item['kind'] == 'assessment'
        assert item['assessment']['sendingAuthorized'] is False
        assert item['assessment']['effectiveDecision'] != 'SEND_READY'
    page = reviews.list_candidates(env.claims, task_id=scope['task_id'])
    assert len(page['items']) == 2
    assert all(item['assessment']['id'] and item['status'] == 'PENDING_REVIEW'
               and item['sourceStatus'] == 'UNVERIFIED' for item in page['items'])
    with env.admin.connect() as conn:
        events = conn.execute('SELECT resource,status,output_sha256 FROM pilot_research_resource_events '
            'WHERE tenant_id=%s AND task_id=%s', (env.tenant,scope['task_id'])).fetchall()
    assert sorted(row[0] for row in events) == ['MODEL_CALL','MODEL_CALL','SOURCE_READ']
    assert all(row[1] == 'SUCCEEDED' and len(row[2]) == 64 for row in events)
    def no_second_read(_deadline):
        raise AssertionError('resume must not fetch')
    assert sequence.run(env.claims, **scope, fetcher=no_second_read) == first
    assert model.calls == 2 and reads == ['read']
