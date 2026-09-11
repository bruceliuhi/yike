-- One durable, owner-private permit per logical internal research action.
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
        WHERE conrelid='pilot_research_reservations'::regclass
            AND conname='pilot_research_reservation_task_run_binding') THEN
        ALTER TABLE pilot_research_reservations
            ADD CONSTRAINT pilot_research_reservation_task_run_binding
            UNIQUE (tenant_id,owner_user_id,reservation_id,task_id,run_id);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS pilot_research_resource_events (
    tenant_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    reservation_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    action_id TEXT NOT NULL CHECK (action_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
    permit_id TEXT NOT NULL CHECK (permit_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
    research_generation INTEGER NOT NULL DEFAULT 1 CHECK (research_generation=1),
    resource TEXT NOT NULL CHECK (resource IN ('SOURCE_READ','MODEL_CALL')),
    input_sha256 TEXT NOT NULL CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
    status TEXT NOT NULL DEFAULT 'ISSUED' CHECK (status IN ('ISSUED','SUCCEEDED','FAILED','UNKNOWN')),
    output_sha256 TEXT CHECK (output_sha256 ~ '^[0-9a-f]{64}$'),
    issued_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    deadline_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id,owner_user_id,task_id,run_id,action_id),
    UNIQUE (tenant_id,owner_user_id,permit_id),
    FOREIGN KEY (tenant_id,owner_user_id,reservation_id,task_id,run_id)
        REFERENCES pilot_research_reservations(tenant_id,owner_user_id,reservation_id,task_id,run_id),
    FOREIGN KEY (tenant_id,owner_user_id,task_id,run_id)
        REFERENCES pilot_collection_runs(tenant_id,owner_user_id,task_id,run_id),
    CHECK (deadline_at>=issued_at),
    CHECK ((status='ISSUED' AND output_sha256 IS NULL AND finished_at IS NULL)
        OR (status='SUCCEEDED' AND output_sha256 IS NOT NULL AND finished_at IS NOT NULL)
        OR (status IN ('FAILED','UNKNOWN') AND output_sha256 IS NULL AND finished_at IS NOT NULL))
);

ALTER TABLE pilot_research_resource_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_research_resource_events FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=current_schema()
        AND tablename='pilot_research_reservations' AND policyname='research_reservation_owner_lock') THEN
        CREATE POLICY research_reservation_owner_lock ON pilot_research_reservations FOR UPDATE
            USING (tenant_id=current_setting('yike.tenant_id',true)
                AND owner_user_id=current_setting('yike.user_id',true));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=current_schema()
        AND tablename='pilot_research_resource_events' AND policyname='research_resource_owner') THEN
        CREATE POLICY research_resource_owner ON pilot_research_resource_events
            USING (tenant_id=current_setting('yike.tenant_id',true)
                AND owner_user_id=current_setting('yike.user_id',true))
            WITH CHECK (tenant_id=current_setting('yike.tenant_id',true)
                AND owner_user_id=current_setting('yike.user_id',true));
    END IF;
END $$;

CREATE OR REPLACE FUNCTION pilot_research_resource_transition() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN
    IF (to_jsonb(NEW)-ARRAY['status','output_sha256','finished_at'])
            IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['status','output_sha256','finished_at'])
        OR OLD.status<>'ISSUED' OR NEW.status='ISSUED' THEN
        RAISE EXCEPTION USING ERRCODE='YT031', MESSAGE='research_resource_immutable';
    END IF;
    NEW.finished_at := clock_timestamp();
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS pilot_research_resource_transition ON pilot_research_resource_events;
CREATE TRIGGER pilot_research_resource_transition BEFORE UPDATE ON pilot_research_resource_events
    FOR EACH ROW EXECUTE FUNCTION pilot_research_resource_transition();
