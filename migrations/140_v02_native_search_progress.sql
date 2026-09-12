-- Committed native Bilibili search heads. Device progress remains a signed claim.
CREATE TABLE IF NOT EXISTS pilot_native_search_progress (
    tenant_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    plan_id TEXT NOT NULL,
    profile_version_id TEXT NOT NULL,
    strategy_version_id TEXT NOT NULL,
    platform TEXT NOT NULL CHECK (platform='BILIBILI'),
    connection_id TEXT NOT NULL,
    connection_version INTEGER NOT NULL CHECK (connection_version BETWEEN 1 AND 2147483647),
    adapter_version TEXT NOT NULL CHECK (adapter_version='bili-search-items-v1'),
    query TEXT NOT NULL CHECK (char_length(query) BETWEEN 1 AND 80),
    cursor JSONB NOT NULL CHECK (jsonb_typeof(cursor)='object'),
    revision INTEGER NOT NULL CHECK (revision BETWEEN 1 AND 2147483647),
    head_batch_request_id TEXT NOT NULL
        CHECK (head_batch_request_id ~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (
        tenant_id,owner_user_id,plan_id,profile_version_id,strategy_version_id,
        platform,connection_id,connection_version,adapter_version,query
    ),
    FOREIGN KEY (tenant_id,owner_user_id) REFERENCES pilot_users(tenant_id,user_id),
    FOREIGN KEY (tenant_id,owner_user_id,plan_id)
        REFERENCES pilot_monitor_plans(tenant_id,owner_user_id,plan_id)
);

ALTER TABLE pilot_native_search_progress ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_native_search_progress FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
         WHERE schemaname=current_schema() AND tablename='pilot_native_search_progress'
           AND policyname='native_search_progress_owner'
    ) THEN
        CREATE POLICY native_search_progress_owner ON pilot_native_search_progress
            USING (tenant_id=current_setting('yike.tenant_id',true)
                AND owner_user_id=current_setting('yike.user_id',true))
            WITH CHECK (tenant_id=current_setting('yike.tenant_id',true)
                AND owner_user_id=current_setting('yike.user_id',true));
    END IF;
END $$;

CREATE OR REPLACE FUNCTION pilot_native_search_progress_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP='DELETE' THEN
        RAISE EXCEPTION 'native search progress cannot be deleted';
    END IF;
    IF (to_jsonb(NEW)-ARRAY['cursor','revision','head_batch_request_id','updated_at'])
        IS DISTINCT FROM
       (to_jsonb(OLD)-ARRAY['cursor','revision','head_batch_request_id','updated_at'])
       OR NEW.revision<>OLD.revision+1
       OR NEW.head_batch_request_id=OLD.head_batch_request_id THEN
        RAISE EXCEPTION 'invalid native search progress update';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS pilot_native_search_progress_guard ON pilot_native_search_progress;
CREATE TRIGGER pilot_native_search_progress_guard
    BEFORE UPDATE OR DELETE ON pilot_native_search_progress
    FOR EACH ROW EXECUTE FUNCTION pilot_native_search_progress_guard();
