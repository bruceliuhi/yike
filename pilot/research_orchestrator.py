"""Internal sequential research pilot; never scheduling, sending or settlement."""
from uuid import UUID, uuid5

from pilot.candidate_ingestion import CandidateIngestionError
from pilot.execution_contract import ExecutionRuntimeError, canonical_uuid


class ResearchOrchestrator:
    def __init__(self, sources, reviews, *, fetcher=None):
        self.sources, self.reviews = sources, reviews
        self.fetcher = fetcher

    @staticmethod
    def _source_action(task_id, run_id):
        return str(uuid5(UUID(run_id), 'research-v2ex-sequence-v1:'+task_id))

    @staticmethod
    def _review_action(task_id, run_id, item):
        return str(uuid5(UUID(run_id), 'research-assess-v1:'+task_id+':'+
            item['candidate_id']+':'+item['version_id']+':'+item['observation_id']))

    def inspect(self, claims, *, task_id, run_id):
        """Read persisted sequence evidence only; never creates permits or reviews."""
        task_id, run_id = canonical_uuid(task_id), canonical_uuid(run_id)
        task = self.sources.resources.runtime.get_task(claims, task_id)
        if task['run_id'] != run_id or [p['platform'] for p in task['platform_runs']] != ['PUBLIC_WEB']:
            raise ExecutionRuntimeError('task_unavailable', 409)
        action = self._source_action(task_id, run_id)
        try:
            source_event = self.sources.resources.get(claims, task_id=task_id,
                run_id=run_id, action_id=action)
        except ExecutionRuntimeError as error:
            if (error.code, error.status) != ('request_not_found', 404):
                raise
            source_event = None
        receipt = self.sources.get_receipt(claims, task_id=task_id, run_id=run_id,
            action_id=action) if source_event and source_event['status'] == 'SUCCEEDED' else None
        items = receipt.get('items', []) if type(receipt) is dict else []
        reviews, missing, skipped = [], [], 0
        for item in items:
            request_id = self._review_action(task_id, run_id, item)
            try:
                review = self.reviews.get_request(claims, request_id)
            except CandidateIngestionError as error:
                if (error.code, error.status) != ('request_not_found', 404):
                    raise
                payload = self._current_payload(claims, task, receipt, item, request_id)
                if payload is None:
                    skipped += 1
                else:
                    missing.append((item, payload))
                continue
            reviews.append(review)
        return dict(task=task, source_action=action, source_event=source_event,
            receipt=receipt, items=items, reviews=reviews, missing=missing, skipped=skipped)

    def advance_one(self, claims, *, task_id, run_id):
        """Perform at most one new source read or model assessment."""
        state = self.inspect(claims, task_id=task_id, run_id=run_id)
        event = state['source_event']
        if event is None:
            self.sources.read_public(claims, task_id=task_id, run_id=run_id,
                action_id=state['source_action'], fetcher=self.fetcher)
            return self.inspect(claims, task_id=task_id, run_id=run_id)
        if event['status'] != 'SUCCEEDED' or state['receipt'] is None:
            return state
        if state['missing']:
            item, payload = state['missing'][0]
            self.reviews.assess_research(claims, payload, task_id=task_id, run_id=run_id,
                observation_id=item['observation_id'])
            return self.inspect(claims, task_id=task_id, run_id=run_id)
        return state

    def run(self, claims, *, task_id, run_id, fetcher=None):
        task_id, run_id = canonical_uuid(task_id), canonical_uuid(run_id)
        task = self.sources.resources.runtime.get_task(claims, task_id)
        if task['run_id'] != run_id or [p['platform'] for p in task['platform_runs']] != ['PUBLIC_WEB']:
            raise ExecutionRuntimeError('task_unavailable', 409)
        source_action = self._source_action(task_id, run_id)
        # The source store checks current authority for fresh work and returns
        # persisted history for an old action, even when the task was canceled.
        source = self.sources.read_public(claims, task_id=task_id, run_id=run_id,
            action_id=source_action, fetcher=fetcher)
        result = dict(schema_version='research-sequence-v1', task_id=task_id, run_id=run_id,
            source_event=source['event'], phase='SOURCE_PENDING', accepted_originals=0,
            analyzed_originals=0, skipped_originals=0, review_results=[], stop_code=None,
            sending_authorized=False)
        if source['event']['status'] != 'SUCCEEDED':
            return result
        receipt = source['receipt']
        if (not isinstance(receipt, dict) or receipt.get('task_id') != task_id
                or receipt.get('run_id') != run_id or receipt.get('request_id') != source_action
                or type(receipt.get('accepted_count')) is not int
                or not 0 <= receipt['accepted_count'] <= 100
                or len(receipt.get('items', [])) != receipt['accepted_count']):
            raise ExecutionRuntimeError('resource_unavailable', 503)
        result['accepted_originals'] = receipt['accepted_count']
        if not receipt['items']:
            result['phase'] = 'NO_ORIGINALS'
            return result
        for item in receipt['items']:
            # An immutable source receipt, not current UI state, selects the
            # original review identity. There is never an automatic retryOf.
            request_id = self._review_action(task_id, run_id, item)
            try:
                try:
                    review = self.reviews.get_request(claims, request_id)
                except CandidateIngestionError as error:
                    if error.code != 'request_not_found' or error.status != 404:
                        raise
                    payload = self._current_payload(claims, task, receipt, item, request_id)
                    if payload is None:
                        result['skipped_originals'] += 1
                        continue
                    review = self.reviews.assess_research(claims, payload, task_id=task_id,
                        run_id=run_id, observation_id=item['observation_id'])
                if review['kind'] != 'assessment':
                    result['review_results'].append(review)
                    result.update(phase='STOPPED', stop_code='assessment_not_ready')
                    return result
                expected_binding = dict(candidateId=item['candidate_id'], candidateRevision=item['revision'],
                    sourceVersionId=item['version_id'], profileId=task['profile_version_id'])
                if (review.get('requestId') != request_id or review.get('candidateId') != item['candidate_id']
                        or any(review['assessment'].get(key) != value for key, value in expected_binding.items())):
                    raise ExecutionRuntimeError('request_conflict', 409)
                result['review_results'].append(review)
                result['analyzed_originals'] += 1
            except (CandidateIngestionError, ExecutionRuntimeError) as error:
                # A revoked caller must not receive even earlier partial data.
                if error.status in (401, 403):
                    raise
                result.update(phase='STOPPED', stop_code=error.code)
                return result
        result['phase'] = 'PARTIAL' if result['skipped_originals'] else 'ANALYZED'
        return result

    def _current_payload(self, claims, task, receipt, item, request_id):
        detail = self.reviews.get_candidate(claims, item['candidate_id'])
        raw = detail['candidate']
        if (raw['ambiguous'] or raw['candidate_id'] != item['candidate_id']
                or raw['revision'] != item['revision']
                or raw['current_version']['version_id'] != item['version_id']
                or raw['current_observation_id'] != item['observation_id']
                or raw['platform'] != 'PUBLIC_WEB'
                or raw['profile_version_id'] != task['profile_version_id']
                or raw['strategy_version_id'] != task['strategy_version_id']):
            return None
        observation = next((value for value in detail['observations']['items']
            if value['observation_id'] == item['observation_id']), None)
        expected = {key: receipt[key] for key in ('task_id', 'run_id', 'platform_run_id', 'request_id')}
        if observation is None or any(observation.get(key) != value for key, value in expected.items()):
            return None
        context = observation['execution_context']
        if (context.get('kind') != 'research-resource-v1'
                or context.get('action_id') != receipt['request_id']
                or context.get('task_id') != receipt['task_id'] or context.get('run_id') != receipt['run_id']):
            return None
        page = self.reviews.list_candidates(claims, ids=[item['candidate_id']], page_size=1)
        if len(page['items']) != 1:
            return None
        view = page['items'][0]
        if (not view['currentBindingValid'] or view['status'] != 'PENDING_REVIEW'
                or view['id'] != item['candidate_id'] or view['revision'] != item['revision']
                or view['sourceVersionId'] != item['version_id']
                or view['profileId'] != raw['profile_version_id']
                or view['strategyVersionId'] != raw['strategy_version_id']):
            return None
        return dict(requestId=request_id, action='ASSESS', candidateId=view['id'],
            candidateRevision=view['revision'], sourceVersionId=view['sourceVersionId'],
            profileId=view['profileId'], profileVersion=view['profileVersion'])
