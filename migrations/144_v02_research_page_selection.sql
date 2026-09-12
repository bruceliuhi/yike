-- Extend the durable research candidate binding with evidence-bound page selection.
CREATE OR REPLACE FUNCTION pilot_research_candidate_binding() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE context JSONB := NEW.execution_context;
DECLARE selection JSONB := context->'page_selection';
DECLARE key_count INTEGER := (SELECT count(*) FROM jsonb_object_keys(context));
BEGIN
    IF context->>'kind' IS DISTINCT FROM 'research-resource-v1' AND NOT EXISTS (
        SELECT 1 FROM pilot_research_reservations q
        WHERE q.tenant_id=NEW.tenant_id AND q.owner_user_id=NEW.owner_user_id
          AND q.task_id=NEW.task_id AND q.run_id=NEW.run_id
    ) THEN
        RETURN NEW;
    END IF;
    IF key_count NOT IN (20,22)
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
           AND (context->>'observed_count')::INTEGER BETWEEN 0 AND 100
           AND (context->>'accepted_count')::INTEGER BETWEEN 0 AND 100
           AND (context->>'skipped_invalid_count')::INTEGER BETWEEN 0 AND 100
           AND (context->>'skipped_budget_count')::INTEGER BETWEEN 0 AND 100
           AND (
             (key_count=20
              AND (context->>'observed_count')::INTEGER=(context->>'accepted_count')::INTEGER
                +(context->>'skipped_invalid_count')::INTEGER+(context->>'skipped_budget_count')::INTEGER)
             OR
             (key_count=22
              AND t.configuration_snapshot->'configuration'->>'publicSource'='public-web-agent-v1'
              AND jsonb_typeof(context->'skipped_background_count')='number'
              AND (context->>'skipped_background_count')::INTEGER BETWEEN 0 AND 1
              AND (SELECT count(*) FROM jsonb_object_keys(selection))=6
              AND selection->>'schema_version'='research-page-selection-v1'
              AND jsonb_typeof(selection->'url')='string'
              AND jsonb_typeof(selection->'content_sha256')='string'
              AND jsonb_typeof(selection->'decision')='string'
              AND jsonb_typeof(selection->'reason')='string'
              AND jsonb_typeof(selection->'quote')='string'
              AND char_length(selection->>'quote') BETWEEN 1 AND 400
              AND btrim(selection->>'quote')<>''
              AND (context->>'observed_count')::INTEGER=1
              AND (context->>'observed_count')::INTEGER=(context->>'accepted_count')::INTEGER
                +(context->>'skipped_invalid_count')::INTEGER+(context->>'skipped_budget_count')::INTEGER
                +(context->>'skipped_background_count')::INTEGER
              AND (
                (selection->>'decision'='ASSESS'
                 AND selection->>'reason' IN ('POSSIBLE_DEMAND','UNCERTAIN')
                 AND (context->>'skipped_background_count')::INTEGER=0)
                OR
                (selection->>'decision'='BACKGROUND'
                 AND selection->>'reason' IN ('INDEX','VENDOR_CONTENT','NO_BUYER_SIGNAL','STALE_OR_CLOSED','IRRELEVANT')
                 AND (context->>'accepted_count')::INTEGER=0
                 AND (context->>'skipped_invalid_count')::INTEGER=0
                 AND (context->>'skipped_budget_count')::INTEGER=0
                 AND (context->>'skipped_background_count')::INTEGER=1)
              )
             )
           )
    ) THEN
        RAISE EXCEPTION 'research candidate binding mismatch';
    END IF;
    -- Keep the legacy 20-key path free of journal privileges. Only the new
    -- dynamic selection form binds its quote and identity to the journal.
    IF key_count=22 AND NOT EXISTS (
        SELECT 1 FROM pilot_research_effect_journal j
         WHERE j.tenant_id=NEW.tenant_id AND j.owner_user_id=NEW.owner_user_id
           AND j.task_id=NEW.task_id AND j.run_id=NEW.run_id
           AND j.action_id=NEW.request_id AND j.status='SUCCEEDED' AND j.kind='READ'
           AND j.output_sha256=context->>'output_sha256'
           AND selection->>'url'=j.result->'evidence'->>'url'
           AND selection->>'content_sha256'=j.result->'evidence'->>'content_sha256'
           AND strpos(j.result->'evidence'->>'text',selection->>'quote')>0
    ) THEN
        RAISE EXCEPTION 'research candidate binding mismatch';
    END IF;
    RETURN NEW;
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN
    RAISE EXCEPTION 'research candidate binding mismatch';
END $$;
