-- Research candidate batches must be the atomic result of their admitted SOURCE_READ.
CREATE OR REPLACE FUNCTION pilot_research_candidate_binding() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE context JSONB := NEW.execution_context;
BEGIN
    IF context->>'kind' IS DISTINCT FROM 'research-resource-v1' AND NOT EXISTS (
        SELECT 1 FROM pilot_research_reservations q
        WHERE q.tenant_id=NEW.tenant_id AND q.owner_user_id=NEW.owner_user_id
          AND q.task_id=NEW.task_id AND q.run_id=NEW.run_id
    ) THEN
        RETURN NEW;
    END IF;
    IF (SELECT count(*) FROM jsonb_object_keys(context))<>20
        OR context->>'kind' IS DISTINCT FROM 'research-resource-v1' OR NOT EXISTS (
        SELECT 1
          FROM pilot_collection_tasks t
          JOIN pilot_collection_runs r ON r.tenant_id=t.tenant_id AND r.owner_user_id=t.owner_user_id
            AND r.task_id=t.task_id AND r.run_id=NEW.run_id
          JOIN pilot_collection_platform_runs p ON p.tenant_id=t.tenant_id
            AND p.owner_user_id=t.owner_user_id AND p.task_id=t.task_id AND p.run_id=r.run_id
            AND p.platform_run_id=NEW.platform_run_id
          JOIN pilot_research_resource_events e ON e.tenant_id=t.tenant_id
            AND e.owner_user_id=t.owner_user_id AND e.task_id=t.task_id AND e.run_id=r.run_id
            AND e.action_id=NEW.request_id
         WHERE t.tenant_id=NEW.tenant_id AND t.owner_user_id=NEW.owner_user_id AND t.task_id=NEW.task_id
           AND NEW.platform='PUBLIC_WEB' AND NEW.profile_version_id=t.profile_version_id
           AND NEW.strategy_version_id=t.strategy_version_id
           AND p.platform='PUBLIC_WEB' AND p.access_mode='PUBLIC_ANONYMOUS'
           AND p.connection_id IS NULL AND p.connection_version IS NULL
           AND context->>'device_id'=t.device_id AND context->>'device_id'=r.device_id
           AND context->>'device_id'=p.device_id
           AND context->>'task_id'=t.task_id AND context->>'run_id'=r.run_id
           AND context->>'platform_run_id'=p.platform_run_id
           AND jsonb_typeof(context->'credential_version')='number'
           AND (context->>'credential_version')::INTEGER=p.credential_version
           AND context->>'access_mode'='PUBLIC_ANONYMOUS'
           AND context->'connection_id'='null'::jsonb AND context->'connection_version'='null'::jsonb
           AND context->>'reservation_id'=e.reservation_id
           AND context->>'action_id'=e.action_id AND context->>'permit_id'=e.permit_id
           AND jsonb_typeof(context->'research_generation')='number'
           AND (context->>'research_generation')::INTEGER=e.research_generation
           AND context->>'resource'=e.resource AND context->>'input_sha256'=e.input_sha256
           AND context->>'output_sha256'=e.output_sha256
           AND e.status='SUCCEEDED' AND e.resource='SOURCE_READ'
           AND jsonb_typeof(context->'observed_count')='number'
           AND jsonb_typeof(context->'accepted_count')='number'
           AND jsonb_typeof(context->'skipped_invalid_count')='number'
           AND jsonb_typeof(context->'skipped_budget_count')='number'
           AND (context->>'accepted_count')::INTEGER=NEW.accepted_count
           AND (context->>'observed_count')::INTEGER=(context->>'accepted_count')::INTEGER
             +(context->>'skipped_invalid_count')::INTEGER+(context->>'skipped_budget_count')::INTEGER
           AND (context->>'observed_count')::INTEGER BETWEEN 0 AND 100
           AND (context->>'accepted_count')::INTEGER BETWEEN 0 AND 100
           AND (context->>'skipped_invalid_count')::INTEGER BETWEEN 0 AND 100
           AND (context->>'skipped_budget_count')::INTEGER BETWEEN 0 AND 100
    ) THEN
        RAISE EXCEPTION 'research candidate binding mismatch';
    END IF;
    RETURN NEW;
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN
    RAISE EXCEPTION 'research candidate binding mismatch';
END $$;

DROP TRIGGER IF EXISTS research_candidate_binding ON pilot_candidate_batches;
CREATE CONSTRAINT TRIGGER research_candidate_binding AFTER INSERT ON pilot_candidate_batches
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION pilot_research_candidate_binding();
