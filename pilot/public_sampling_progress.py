"""Read committed public-source sampling progress from existing immutable facts."""
from pilot.execution_contract import MAX_VERSION, ExecutionRuntimeError, canonical_uuid


PUBLIC_SOURCE_IDS = frozenset({
    "v2ex-latest-v1",
    "v2ex-qna-v1",
    "v2ex-outsourcing-authors-v1",
})


def committed_public_sampling_round(cursor, *, tenant_id, owner_user_id, task, platform, version=1):
    if type(version) is not int or version not in (1, 2):
        raise ExecutionRuntimeError('invalid_request', 422)
    if (platform.get("platform") != "PUBLIC_WEB"
            or platform.get("access_mode") != "PUBLIC_ANONYMOUS"):
        raise ExecutionRuntimeError("capability_unavailable", 409)
    cursor.execute(
        """
        SELECT o.plan_id,t.configuration_snapshot
          FROM pilot_collection_tasks t
          JOIN pilot_collection_runs r
            ON r.tenant_id=t.tenant_id AND r.owner_user_id=t.owner_user_id
           AND r.task_id=t.task_id
          JOIN pilot_collection_platform_runs current_platform
            ON current_platform.tenant_id=r.tenant_id
           AND current_platform.owner_user_id=r.owner_user_id
           AND current_platform.task_id=r.task_id AND current_platform.run_id=r.run_id
          JOIN pilot_monitor_occurrences o
            ON o.tenant_id=r.tenant_id AND o.owner_user_id=r.owner_user_id
           AND o.task_id=r.task_id AND o.run_id=r.run_id AND o.status='STARTED'
          JOIN pilot_monitor_plans plan
            ON plan.tenant_id=o.tenant_id AND plan.owner_user_id=o.owner_user_id
           AND plan.plan_id=o.plan_id
           AND plan.profile_version_id=t.profile_version_id
           AND plan.strategy_version_id=t.strategy_version_id
           AND plan.configuration_sha256=t.configuration_sha256
         WHERE t.tenant_id=%s AND t.owner_user_id=%s AND t.task_id=%s
           AND r.run_id=%s AND current_platform.platform_run_id=%s
           AND current_platform.platform='PUBLIC_WEB'
           AND current_platform.access_mode='PUBLIC_ANONYMOUS'
        """,
        (tenant_id, owner_user_id, task["task_id"], platform["run_id"], platform["platform_run_id"]),
    )
    current = cursor.fetchone()
    if current is None:
        raise ExecutionRuntimeError("capability_unavailable", 409)
    plan_id = canonical_uuid(current[0])
    configuration = current[1].get("configuration") if type(current[1]) is dict else None
    if type(configuration) is not dict:
        raise ExecutionRuntimeError("capability_unavailable", 409)
    source_id = configuration.get("publicSource")
    if configuration.get("mode") != "monitor" or source_id not in PUBLIC_SOURCE_IDS:
        raise ExecutionRuntimeError("capability_unavailable", 409)
    cursor.execute(
        """
        SELECT count(DISTINCT b.platform_run_id)
          FROM pilot_candidate_batches b
          JOIN pilot_monitor_occurrences o
            ON o.tenant_id=b.tenant_id AND o.owner_user_id=b.owner_user_id
           AND o.task_id=b.task_id AND o.run_id=b.run_id
          JOIN pilot_collection_tasks prior_task
            ON prior_task.tenant_id=b.tenant_id AND prior_task.owner_user_id=b.owner_user_id
           AND prior_task.task_id=b.task_id
          JOIN pilot_collection_platform_runs prior_platform
            ON prior_platform.tenant_id=b.tenant_id AND prior_platform.owner_user_id=b.owner_user_id
           AND prior_platform.task_id=b.task_id AND prior_platform.run_id=b.run_id
           AND prior_platform.platform_run_id=b.platform_run_id
         WHERE b.tenant_id=%s AND b.owner_user_id=%s AND o.plan_id=%s
           AND b.profile_version_id=%s AND b.strategy_version_id=%s
           AND prior_task.profile_version_id=b.profile_version_id
           AND prior_task.strategy_version_id=b.strategy_version_id
           AND prior_task.configuration_snapshot->'configuration'->>'publicSource'=%s
           AND b.platform='PUBLIC_WEB'
           AND prior_platform.platform='PUBLIC_WEB'
           AND prior_platform.access_mode='PUBLIC_ANONYMOUS'
           AND b.execution_context->>'access_mode'='PUBLIC_ANONYMOUS'
           AND b.platform_run_id<>%s
        """,
        (tenant_id, owner_user_id, plan_id, task["profile_version_id"], task["strategy_version_id"],
         source_id, platform["platform_run_id"]),
    )
    round_number = cursor.fetchone()[0]
    if type(round_number) is not int or not 0 <= round_number <= MAX_VERSION:
        raise ExecutionRuntimeError("sampling_round_exhausted", 409)
    result = {
        "schema_version": f"public-sampling-round-v{version}",
        "plan_id": plan_id,
        "source_id": source_id,
        "round": round_number,
    }
    if version == 2:
        from pilot.public_source_revisit import choose_revisit
        result['revisit'] = (choose_revisit(cursor, tenant_id=tenant_id, owner_user_id=owner_user_id,
            task=task, plan_id=plan_id, configuration=configuration)
            if source_id == 'v2ex-outsourcing-authors-v1' and round_number % 2 else None)
    return result
