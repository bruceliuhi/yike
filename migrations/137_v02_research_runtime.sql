-- Durable coordinator for bounded ordinary-client research advancement.
CREATE TABLE IF NOT EXISTS pilot_research_runtime (
    tenant_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    generation INTEGER NOT NULL DEFAULT 0 CHECK (generation BETWEEN 0 AND 2147483647),
    current_owner TEXT,
    lease_expires_at TIMESTAMPTZ,
    phase TEXT NOT NULL DEFAULT 'QUEUED' CHECK (phase IN ('QUEUED','RUNNING','STOPPED','CANCELED','COMPLETED')),
    stop_code TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id,owner_user_id,task_id),
    UNIQUE (tenant_id,owner_user_id,task_id,run_id),
    FOREIGN KEY (tenant_id,owner_user_id,task_id,run_id)
        REFERENCES pilot_collection_runs(tenant_id,owner_user_id,task_id,run_id),
    CHECK ((current_owner IS NULL)=(lease_expires_at IS NULL))
);

ALTER TABLE pilot_research_runtime ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_research_runtime FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=current_schema()
        AND tablename='pilot_research_runtime' AND policyname='research_runtime_owner') THEN
        CREATE POLICY research_runtime_owner ON pilot_research_runtime
            USING (tenant_id=current_setting('yike.tenant_id',true)
                AND owner_user_id=current_setting('yike.user_id',true))
            WITH CHECK (tenant_id=current_setting('yike.tenant_id',true)
                AND owner_user_id=current_setting('yike.user_id',true));
    END IF;
END $$;
