-- Immutable, non-secret resource reservation bound atomically to one research START.
CREATE TABLE IF NOT EXISTS pilot_research_reservations (
    tenant_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    reservation_id TEXT NOT NULL CHECK (reservation_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
    quote_id TEXT NOT NULL CHECK (quote_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
    request_id TEXT NOT NULL CHECK (request_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
    task_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    draft_id TEXT NOT NULL,
    draft_revision INTEGER NOT NULL CHECK (draft_revision BETWEEN 1 AND 2147483647),
    strategy_version_id TEXT NOT NULL,
    profile_version_id TEXT NOT NULL,
    configuration_sha256 TEXT NOT NULL CHECK (configuration_sha256 ~ '^[0-9a-f]{64}$'),
    configuration_hash TEXT NOT NULL CHECK (configuration_hash ~ '^[0-9a-f]{64}$'),
    rule_version TEXT NOT NULL CHECK (length(rule_version) BETWEEN 1 AND 512),
    rule_sha256 TEXT NOT NULL CHECK (rule_sha256 ~ '^[0-9a-f]{64}$'),
    quote_sha256 TEXT NOT NULL CHECK (quote_sha256 ~ '^[0-9a-f]{64}$'),
    authorization_token_sha256 TEXT NOT NULL CHECK (authorization_token_sha256 ~ '^[0-9a-f]{64}$'),
    estimated_soubei INTEGER NOT NULL CHECK (estimated_soubei BETWEEN 1 AND 1000000),
    max_soubei INTEGER NOT NULL CHECK (max_soubei BETWEEN estimated_soubei AND 1000000),
    source_limit INTEGER NOT NULL CHECK (source_limit BETWEEN 1 AND 1000000),
    minute_limit INTEGER NOT NULL CHECK (minute_limit BETWEEN 1 AND 1000000),
    model_call_limit INTEGER NOT NULL CHECK (model_call_limit BETWEEN 1 AND 1000000),
    status TEXT NOT NULL CHECK (status='RESERVED'),
    receipt JSONB NOT NULL CHECK (jsonb_typeof(receipt)='object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id,owner_user_id,reservation_id),
    UNIQUE (tenant_id,owner_user_id,quote_id),
    UNIQUE (tenant_id,owner_user_id,request_id),
    FOREIGN KEY (tenant_id,owner_user_id,request_id)
        REFERENCES pilot_execution_operations(tenant_id,owner_user_id,request_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (tenant_id,owner_user_id,task_id,run_id)
        REFERENCES pilot_collection_runs(tenant_id,owner_user_id,task_id,run_id),
    FOREIGN KEY (tenant_id,owner_user_id,strategy_version_id)
        REFERENCES pilot_research_strategy_versions(tenant_id,owner_user_id,strategy_version_id),
    FOREIGN KEY (tenant_id,profile_version_id)
        REFERENCES business_profile_versions(tenant_id,profile_version_id)
);

ALTER TABLE pilot_research_reservations ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_research_reservations FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=current_schema()
        AND tablename='pilot_research_reservations' AND policyname='research_reservation_owner_select') THEN
        CREATE POLICY research_reservation_owner_select ON pilot_research_reservations FOR SELECT
            USING (tenant_id=current_setting('yike.tenant_id',true)
                AND owner_user_id=current_setting('yike.user_id',true));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=current_schema()
        AND tablename='pilot_research_reservations' AND policyname='research_reservation_owner_insert') THEN
        CREATE POLICY research_reservation_owner_insert ON pilot_research_reservations FOR INSERT
            WITH CHECK (tenant_id=current_setting('yike.tenant_id',true)
                AND owner_user_id=current_setting('yike.user_id',true));
    END IF;
END $$;

CREATE OR REPLACE FUNCTION pilot_research_reservation_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN
    RAISE EXCEPTION USING ERRCODE='YT030', MESSAGE='research_reservation_immutable';
END $$;
DROP TRIGGER IF EXISTS pilot_research_reservation_immutable ON pilot_research_reservations;
CREATE TRIGGER pilot_research_reservation_immutable BEFORE UPDATE ON pilot_research_reservations
    FOR EACH ROW EXECUTE FUNCTION pilot_research_reservation_immutable();
