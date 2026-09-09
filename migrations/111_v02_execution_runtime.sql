-- Persistent execution authority, separate from legacy research jobs.
CREATE TABLE IF NOT EXISTS pilot_collection_tasks (
    tenant_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    profile_version_id TEXT NOT NULL,
    strategy_version_id TEXT NOT NULL,
    configuration_sha256 TEXT NOT NULL CHECK (configuration_sha256 ~ '^[0-9a-f]{64}$'),
    configuration_snapshot JSONB NOT NULL CHECK (jsonb_typeof(configuration_snapshot)='object'),
    max_records INTEGER NOT NULL CHECK (max_records BETWEEN 1 AND 10000),
    max_runtime_seconds INTEGER NOT NULL CHECK (max_runtime_seconds BETWEEN 1 AND 86400),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    deadline_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','RUNNING','CANCELLING','CANCELED')),
    PRIMARY KEY (tenant_id,owner_user_id,task_id),
    UNIQUE (tenant_id,owner_user_id,task_id,device_id,profile_version_id),
    FOREIGN KEY (tenant_id,owner_user_id,device_id) REFERENCES pilot_devices(tenant_id,owner_user_id,device_id),
    FOREIGN KEY (tenant_id,profile_version_id) REFERENCES business_profile_versions(tenant_id,profile_version_id),
    CHECK (deadline_at=created_at + max_runtime_seconds * interval '1 second')
);

CREATE TABLE IF NOT EXISTS pilot_collection_runs (
    tenant_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    profile_version_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','RUNNING','CANCELLING','CANCELED')),
    PRIMARY KEY (tenant_id,owner_user_id,task_id,run_id),
    UNIQUE (tenant_id,owner_user_id,task_id),
    UNIQUE (tenant_id,owner_user_id,task_id,run_id,device_id,profile_version_id),
    FOREIGN KEY (tenant_id,owner_user_id,task_id,device_id,profile_version_id)
        REFERENCES pilot_collection_tasks(tenant_id,owner_user_id,task_id,device_id,profile_version_id)
);

CREATE TABLE IF NOT EXISTS pilot_collection_platform_runs (
    tenant_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    platform_run_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    profile_version_id TEXT NOT NULL,
    platform TEXT NOT NULL CHECK (platform IN ('XIAOHONGSHU','DOUYIN','BILIBILI','ZHIHU','PUBLIC_WEB')),
    target_order INTEGER NOT NULL CHECK (target_order BETWEEN 0 AND 4),
    access_mode TEXT NOT NULL CHECK (access_mode IN ('PLATFORM_ACCOUNT','PUBLIC_ANONYMOUS')),
    connection_id TEXT,
    connection_version INTEGER CHECK (connection_version BETWEEN 1 AND 2147483647),
    credential_version INTEGER NOT NULL CHECK (credential_version BETWEEN 1 AND 2147483647),
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','RUNNING','CANCELLING','CANCELED')),
    lease_id TEXT,
    execution_generation INTEGER NOT NULL DEFAULT 0 CHECK (execution_generation BETWEEN 0 AND 2147483647),
    lease_expires_at TIMESTAMPTZ,
    records_used INTEGER NOT NULL DEFAULT 0 CHECK (records_used BETWEEN 0 AND 2147483647),
    PRIMARY KEY (tenant_id,owner_user_id,task_id,run_id,platform_run_id),
    UNIQUE (tenant_id,owner_user_id,task_id,run_id,platform),
    UNIQUE (tenant_id,owner_user_id,task_id,run_id,target_order),
    FOREIGN KEY (tenant_id,owner_user_id,task_id,run_id,device_id,profile_version_id)
        REFERENCES pilot_collection_runs(tenant_id,owner_user_id,task_id,run_id,device_id,profile_version_id),
    FOREIGN KEY (tenant_id,device_id,connection_id) REFERENCES pilot_platform_connections(tenant_id,device_id,connection_id),
    CHECK ((access_mode='PLATFORM_ACCOUNT' AND connection_id IS NOT NULL AND connection_version IS NOT NULL)
        OR (access_mode='PUBLIC_ANONYMOUS' AND platform='PUBLIC_WEB' AND connection_id IS NULL AND connection_version IS NULL)),
    CHECK ((execution_generation=0 AND lease_id IS NULL AND lease_expires_at IS NULL)
        OR (execution_generation>0 AND lease_id IS NOT NULL AND lease_expires_at IS NOT NULL)),
    CHECK (status<>'RUNNING' OR execution_generation>0)
);

CREATE TABLE IF NOT EXISTS pilot_execution_operations (
    tenant_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    request_id TEXT NOT NULL CHECK (request_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
    operation TEXT NOT NULL CHECK (operation IN ('START','CLAIM','RENEW','CANCEL')),
    operation_sha256 TEXT NOT NULL CHECK (operation_sha256 ~ '^[0-9a-f]{64}$'),
    task_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    receipt JSONB NOT NULL CHECK (jsonb_typeof(receipt)='object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id,owner_user_id,request_id),
    FOREIGN KEY (tenant_id,owner_user_id,task_id,run_id)
        REFERENCES pilot_collection_runs(tenant_id,owner_user_id,task_id,run_id)
);

CREATE OR REPLACE FUNCTION pilot_execution_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME='pilot_execution_operations' THEN
        RAISE EXCEPTION 'execution receipt is immutable';
    ELSIF TG_TABLE_NAME IN ('pilot_collection_tasks','pilot_collection_runs') THEN
        IF (to_jsonb(NEW)-'status') IS DISTINCT FROM (to_jsonb(OLD)-'status') THEN
            RAISE EXCEPTION 'execution snapshot is immutable';
        END IF;
    ELSIF (to_jsonb(NEW)-ARRAY['status','credential_version','lease_id','execution_generation','lease_expires_at','records_used'])
        IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['status','credential_version','lease_id','execution_generation','lease_expires_at','records_used']) THEN
        RAISE EXCEPTION 'execution binding is immutable';
    END IF;
    IF TG_TABLE_NAME='pilot_collection_platform_runs' THEN
        IF NEW.execution_generation<OLD.execution_generation OR NEW.records_used<OLD.records_used THEN
            RAISE EXCEPTION 'execution counters cannot decrease';
        END IF;
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION pilot_execution_budget() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE budget INTEGER; used BIGINT;
BEGIN
    SELECT max_records INTO budget FROM pilot_collection_tasks
        WHERE tenant_id=NEW.tenant_id AND owner_user_id=NEW.owner_user_id AND task_id=NEW.task_id FOR UPDATE;
    SELECT COALESCE(sum(records_used),0) INTO used FROM pilot_collection_platform_runs
        WHERE tenant_id=NEW.tenant_id AND owner_user_id=NEW.owner_user_id AND task_id=NEW.task_id
            AND platform_run_id<>NEW.platform_run_id;
    IF budget IS NULL OR used+NEW.records_used>budget THEN
        RAISE EXCEPTION 'execution budget exceeded';
    END IF;
    RETURN NEW;
END $$;

DO $$
DECLARE item TEXT;
BEGIN
    FOREACH item IN ARRAY ARRAY['pilot_collection_tasks','pilot_collection_runs','pilot_collection_platform_runs','pilot_execution_operations'] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',item);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',item);
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=current_schema() AND tablename=item AND policyname='execution_owner') THEN
            EXECUTE format('CREATE POLICY execution_owner ON %I USING (tenant_id=current_setting(''yike.tenant_id'',true) AND owner_user_id=current_setting(''yike.user_id'',true)) WITH CHECK (tenant_id=current_setting(''yike.tenant_id'',true) AND owner_user_id=current_setting(''yike.user_id'',true))',item);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid=item::regclass AND tgname='execution_immutable') THEN
            EXECUTE format('CREATE TRIGGER execution_immutable BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION pilot_execution_immutable()',item);
        END IF;
    END LOOP;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid='pilot_collection_platform_runs'::regclass AND tgname='execution_budget') THEN
        CREATE TRIGGER execution_budget BEFORE INSERT OR UPDATE OF records_used ON pilot_collection_platform_runs
            FOR EACH ROW EXECUTE FUNCTION pilot_execution_budget();
    END IF;
END $$;
