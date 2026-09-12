"""Bounded public revisits derived only from same-scope committed facts."""
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from pilot.execution_contract import ExecutionRuntimeError

SOURCE = 'v2ex-outsourcing-authors-v1'


class PublicSourceRevisit(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra='forbid',
                              hide_input_in_errors=True, revalidate_instances='always')
    schema_version: Literal['public-source-revisit-v1']
    claim_request_id: str
    topic_id: str
    outcome: Literal['READ', 'UNAVAILABLE']

    @field_validator('topic_id')
    @classmethod
    def topic(cls, value):
        if not re.fullmatch(r'[1-9][0-9]{0,15}', value) or int(value) > 9007199254740991:
            raise ValueError('invalid topic')
        return value

    @field_validator('claim_request_id')
    @classmethod
    def claim(cls, value):
        if str(UUID(value)) != value:
            raise ValueError('invalid claim')
        return value


def choose_revisit(cursor, *, tenant_id, owner_user_id, task, plan_id, configuration):
    cursor.execute(
        """
        WITH scoped AS MATERIALIZED (
            SELECT b.* FROM pilot_candidate_batches b
            JOIN pilot_monitor_occurrences o USING(tenant_id,owner_user_id,task_id,run_id)
            JOIN pilot_collection_tasks t USING(tenant_id,owner_user_id,task_id)
            JOIN pilot_collection_platform_runs p
              ON p.tenant_id=b.tenant_id AND p.owner_user_id=b.owner_user_id
             AND p.task_id=b.task_id AND p.run_id=b.run_id AND p.platform_run_id=b.platform_run_id
            WHERE b.tenant_id=%s AND b.owner_user_id=%s AND o.plan_id=%s
              AND b.profile_version_id=%s AND b.strategy_version_id=%s
              AND t.profile_version_id=b.profile_version_id AND t.strategy_version_id=b.strategy_version_id
              AND t.configuration_snapshot->'configuration'->>'publicSource'=%s
              AND b.platform='PUBLIC_WEB' AND p.platform='PUBLIC_WEB'
              AND p.access_mode='PUBLIC_ANONYMOUS'
              AND b.execution_context->>'access_mode'='PUBLIC_ANONYMOUS'
        ), candidates AS (
            SELECT DISTINCT ON (s.external_source_id)
                   s.external_source_id AS topic_id,ob.query,ob.received_at AS first_seen
            FROM scoped b
            JOIN pilot_candidate_observations ob USING(tenant_id,owner_user_id,platform_run_id,request_id)
            JOIN pilot_candidate_sources s USING(tenant_id,owner_user_id,source_id)
            JOIN pilot_candidate_versions v USING(tenant_id,owner_user_id,source_id,version_id)
            WHERE s.platform='PUBLIC_WEB' AND s.kind='PAGE'
              AND s.external_source_id ~ '^[1-9][0-9]{0,15}$'
              AND (length(s.external_source_id)<16 OR s.external_source_id<='9007199254740991')
              AND v.content->>'public_url'='https://www.v2ex.com/t/'||s.external_source_id
              AND ob.collector_version=%s AND ob.query=ANY(%s)
            ORDER BY s.external_source_id,ob.received_at,ob.query,ob.observation_id
        )
        SELECT c.topic_id,c.query FROM candidates c
        LEFT JOIN LATERAL (
            SELECT max(b.received_at) AS last_seen FROM scoped b
            WHERE b.receipt->'public_revisit'->>'topic_id'=c.topic_id
              AND b.receipt->'public_revisit'->>'schema_version'='public-source-revisit-v1'
              AND b.receipt->'public_revisit'->>'outcome' IN ('READ','UNAVAILABLE')
        ) revisits ON true
        ORDER BY revisits.last_seen NULLS FIRST,c.first_seen,length(c.topic_id),c.topic_id
        LIMIT 1
        """,
        (tenant_id, owner_user_id, plan_id, task['profile_version_id'], task['strategy_version_id'],
         SOURCE, SOURCE, configuration.get('keywords', [])),
    )
    row = cursor.fetchone()
    return None if row is None else {'topic_id': row[0], 'query': row[1]}


def validate_public_revisit(cursor, *, tenant_id, owner_user_id, batch):
    """Return whether the current frozen CLAIM is v2; never recompute its queue."""
    ex = batch.execution
    cursor.execute(
        """
        SELECT e.request_id,e.receipt,t.configuration_snapshot,
               t.device_id,p.credential_version,t.profile_version_id,t.strategy_version_id,
               p.platform,p.access_mode,p.connection_id,p.connection_version
        FROM pilot_execution_operations e
        JOIN pilot_collection_tasks t USING(tenant_id,owner_user_id,task_id)
        JOIN pilot_collection_platform_runs p
          ON p.tenant_id=e.tenant_id AND p.owner_user_id=e.owner_user_id
         AND p.task_id=e.task_id AND p.run_id=e.run_id
        WHERE e.tenant_id=%s AND e.owner_user_id=%s AND e.operation='CLAIM'
          AND e.task_id=%s AND p.platform_run_id=%s
          AND e.receipt->>'platform_run_id'=p.platform_run_id
          AND e.receipt->>'lease_id'=p.lease_id
          AND e.receipt->>'execution_generation'=p.execution_generation::text
        """,
        (tenant_id, owner_user_id, ex.task_id, ex.platform_run_id),
    )
    rows = cursor.fetchall()
    progress = batch.public_revisit
    if len(rows) != 1:
        if progress is not None:
            raise ExecutionRuntimeError('public_revisit_conflict', 409)
        return False
    request_id, receipt, snapshot, *binding = rows[0]
    sampling = receipt.get('public_sampling')
    is_v2 = type(sampling) is dict and sampling.get('schema_version') == 'public-sampling-round-v2'
    if is_v2 or progress is not None:
        if (binding != [ex.device_id, ex.credential_version, batch.profile_version_id,
                        batch.strategy_version_id, batch.platform, ex.access_mode,
                        ex.connection_id, ex.connection_version]
                or any(receipt.get(field) != getattr(ex, field) for field in (
                    'task_id', 'run_id', 'platform_run_id', 'lease_id', 'execution_generation'))):
            raise ExecutionRuntimeError('public_revisit_conflict', 409)
    frozen = sampling.get('revisit') if is_v2 else None
    if frozen is None:
        if progress is not None:
            raise ExecutionRuntimeError('public_revisit_conflict', 409)
        return is_v2
    configuration = snapshot.get('configuration', {})
    if (progress is None or batch.platform != 'PUBLIC_WEB' or ex.access_mode != 'PUBLIC_ANONYMOUS'
            or ex.connection_id is not None or ex.connection_version is not None
            or progress.claim_request_id != request_id or progress.topic_id != frozen.get('topic_id')
            or sampling.get('source_id') != SOURCE or configuration.get('publicSource') != SOURCE
            or frozen.get('query') not in configuration.get('keywords', [])):
        raise ExecutionRuntimeError('public_revisit_conflict', 409)
    matched = [record for record in batch.records if record.external_source_id == progress.topic_id
               or record.public_url == f'https://www.v2ex.com/t/{progress.topic_id}']
    if progress.outcome == 'UNAVAILABLE':
        valid = not matched
    else:
        valid = len(matched) == 1
        if valid:
            record = matched[0]
            valid = (record.kind == 'PAGE' and record.external_source_id == progress.topic_id
                     and record.public_url == f'https://www.v2ex.com/t/{progress.topic_id}'
                     and record.query == frozen['query'] and record.collector_version == SOURCE
                     and record.source_context is not None
                     and record.normalizer_version == 'v2ex-author-page-v1')
    if not valid:
        raise ExecutionRuntimeError('public_revisit_conflict', 409)
    return True
