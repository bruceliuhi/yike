-- Owner-private, unverified raw evidence. No opportunity/review state is created.
CREATE TABLE IF NOT EXISTS pilot_candidate_batches (
    tenant_id TEXT NOT NULL, owner_user_id TEXT NOT NULL,
    platform_run_id TEXT NOT NULL, request_id TEXT NOT NULL
        CHECK (request_id ~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'),
    task_id TEXT NOT NULL, run_id TEXT NOT NULL,
    platform TEXT NOT NULL, profile_version_id TEXT NOT NULL, strategy_version_id TEXT NOT NULL,
    execution_context JSONB NOT NULL CHECK (jsonb_typeof(execution_context)='object'),
    fingerprint TEXT NOT NULL CHECK (fingerprint ~ '^[0-9a-f]{64}$'),
    accepted_count INTEGER NOT NULL CHECK (accepted_count BETWEEN 0 AND 100),
    received_at TIMESTAMPTZ NOT NULL,
    receipt JSONB NOT NULL CHECK (jsonb_typeof(receipt)='object'),
    PRIMARY KEY (tenant_id,platform_run_id,request_id),
    UNIQUE (tenant_id,owner_user_id,platform_run_id,request_id),
    FOREIGN KEY (tenant_id,owner_user_id,task_id,run_id,platform_run_id)
        REFERENCES pilot_collection_platform_runs(tenant_id,owner_user_id,task_id,run_id,platform_run_id)
);
CREATE TABLE IF NOT EXISTS pilot_candidate_sources (
    tenant_id TEXT NOT NULL, owner_user_id TEXT NOT NULL,
    source_id UUID NOT NULL, source_identity TEXT NOT NULL CHECK (source_identity ~ '^[0-9a-f]{64}$'),
    platform TEXT NOT NULL CHECK (platform IN ('XIAOHONGSHU','DOUYIN','BILIBILI','ZHIHU','PUBLIC_WEB')),
    kind TEXT NOT NULL CHECK (kind IN ('POST','COMMENT','PAGE')),
    external_source_id TEXT, external_comment_id TEXT,
    PRIMARY KEY (tenant_id,owner_user_id,source_id),
    UNIQUE (tenant_id,owner_user_id,source_identity),
    FOREIGN KEY (tenant_id,owner_user_id) REFERENCES pilot_users(tenant_id,user_id),
    CHECK ((kind='COMMENT')=(external_comment_id IS NOT NULL)),
    CHECK (kind<>'PAGE' OR platform='PUBLIC_WEB'),
    CHECK (external_source_id IS NOT NULL OR platform='PUBLIC_WEB')
);
CREATE TABLE IF NOT EXISTS pilot_candidate_versions (
    tenant_id TEXT NOT NULL, owner_user_id TEXT NOT NULL, source_id UUID NOT NULL,
    version_id UUID NOT NULL, content_version TEXT NOT NULL CHECK (content_version ~ '^[0-9a-f]{64}$'),
    content JSONB NOT NULL CHECK (jsonb_typeof(content)='object'),
    received_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id,owner_user_id,source_id,version_id),
    UNIQUE (tenant_id,owner_user_id,source_id,content_version),
    FOREIGN KEY (tenant_id,owner_user_id,source_id) REFERENCES pilot_candidate_sources(tenant_id,owner_user_id,source_id)
);
CREATE TABLE IF NOT EXISTS pilot_candidate_projections (
    tenant_id TEXT NOT NULL, owner_user_id TEXT NOT NULL, source_id UUID NOT NULL,
    candidate_id UUID NOT NULL, profile_version_id TEXT NOT NULL, strategy_version_id TEXT NOT NULL,
    version_id UUID NOT NULL, current_observation_id UUID NOT NULL,
    revision BIGINT NOT NULL CHECK (revision>=1), ambiguous BOOLEAN NOT NULL DEFAULT false,
    latest_observed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id,owner_user_id,candidate_id),
    UNIQUE (tenant_id,owner_user_id,profile_version_id,strategy_version_id,source_id),
    UNIQUE (tenant_id,owner_user_id,candidate_id,source_id),
    FOREIGN KEY (tenant_id,owner_user_id,source_id,version_id)
        REFERENCES pilot_candidate_versions(tenant_id,owner_user_id,source_id,version_id),
    FOREIGN KEY (tenant_id,profile_version_id) REFERENCES business_profile_versions(tenant_id,profile_version_id)
);
CREATE TABLE IF NOT EXISTS pilot_candidate_observations (
    tenant_id TEXT NOT NULL, owner_user_id TEXT NOT NULL,
    observation_id UUID NOT NULL, candidate_id UUID NOT NULL, source_id UUID NOT NULL, version_id UUID NOT NULL,
    platform_run_id TEXT NOT NULL, request_id TEXT NOT NULL,
    record_index INTEGER NOT NULL CHECK (record_index BETWEEN 0 AND 99),
    observed_at TIMESTAMPTZ NOT NULL, received_at TIMESTAMPTZ NOT NULL,
    query TEXT, collector_version TEXT NOT NULL, normalizer_version TEXT NOT NULL,
    PRIMARY KEY (tenant_id,owner_user_id,observation_id),
    UNIQUE (tenant_id,owner_user_id,platform_run_id,request_id,record_index),
    UNIQUE (tenant_id,owner_user_id,candidate_id,source_id,version_id,observation_id),
    FOREIGN KEY (tenant_id,owner_user_id,candidate_id,source_id)
        REFERENCES pilot_candidate_projections(tenant_id,owner_user_id,candidate_id,source_id),
    FOREIGN KEY (tenant_id,owner_user_id,source_id,version_id)
        REFERENCES pilot_candidate_versions(tenant_id,owner_user_id,source_id,version_id),
    FOREIGN KEY (tenant_id,owner_user_id,platform_run_id,request_id)
        REFERENCES pilot_candidate_batches(tenant_id,owner_user_id,platform_run_id,request_id) DEFERRABLE INITIALLY DEFERRED
);
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='pilot_candidate_projections'::regclass AND conname='candidate_current_observation') THEN
        ALTER TABLE pilot_candidate_projections ADD CONSTRAINT candidate_current_observation
        FOREIGN KEY (tenant_id,owner_user_id,candidate_id,source_id,version_id,current_observation_id)
        REFERENCES pilot_candidate_observations(tenant_id,owner_user_id,candidate_id,source_id,version_id,observation_id)
        DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS candidate_observation_candidate ON pilot_candidate_observations(tenant_id,owner_user_id,candidate_id,observed_at DESC,observation_id);
-- Cross-table scope must remain valid even if a caller bypasses the service.
CREATE OR REPLACE FUNCTION pilot_candidate_execution_binding() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pilot_candidate_projections p
        JOIN pilot_candidate_sources s USING(tenant_id,owner_user_id,source_id)
        JOIN pilot_candidate_batches b ON b.tenant_id=p.tenant_id AND b.owner_user_id=p.owner_user_id
            AND b.platform_run_id=NEW.platform_run_id AND b.request_id=NEW.request_id
        JOIN pilot_collection_tasks t ON t.tenant_id=b.tenant_id AND t.owner_user_id=b.owner_user_id AND t.task_id=b.task_id
        JOIN pilot_collection_platform_runs r ON r.tenant_id=b.tenant_id AND r.owner_user_id=b.owner_user_id
            AND r.task_id=b.task_id AND r.run_id=b.run_id AND r.platform_run_id=b.platform_run_id
        WHERE p.tenant_id=NEW.tenant_id AND p.owner_user_id=NEW.owner_user_id AND p.candidate_id=NEW.candidate_id
            AND p.profile_version_id=t.profile_version_id AND p.strategy_version_id=t.strategy_version_id
            AND b.profile_version_id=t.profile_version_id AND b.strategy_version_id=t.strategy_version_id AND b.platform=r.platform
            AND s.platform=r.platform AND NEW.record_index<b.accepted_count
    ) THEN RAISE EXCEPTION 'candidate execution binding mismatch'; END IF;
    RETURN NEW;
END $$;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid='pilot_candidate_observations'::regclass AND tgname='candidate_execution_binding') THEN
        CREATE CONSTRAINT TRIGGER candidate_execution_binding AFTER INSERT ON pilot_candidate_observations
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION pilot_candidate_execution_binding();
    END IF;
END $$;
CREATE OR REPLACE FUNCTION pilot_candidate_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME<>'pilot_candidate_projections' THEN
        RAISE EXCEPTION 'candidate evidence is immutable';
    END IF;
    IF (to_jsonb(NEW)-ARRAY['version_id','current_observation_id','revision','ambiguous','latest_observed_at'])
        IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['version_id','current_observation_id','revision','ambiguous','latest_observed_at'])
        OR NEW.revision<OLD.revision OR NEW.latest_observed_at<OLD.latest_observed_at THEN
        RAISE EXCEPTION 'candidate binding is immutable';
    END IF;
    RETURN NEW;
END $$;
DO $$ DECLARE item TEXT; BEGIN
    FOREACH item IN ARRAY ARRAY['pilot_candidate_batches','pilot_candidate_sources','pilot_candidate_versions','pilot_candidate_projections','pilot_candidate_observations'] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',item);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',item);
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=current_schema() AND tablename=item AND policyname='candidate_owner') THEN
            EXECUTE format('CREATE POLICY candidate_owner ON %I USING (tenant_id=current_setting(''yike.tenant_id'',true) AND owner_user_id=current_setting(''yike.user_id'',true)) WITH CHECK (tenant_id=current_setting(''yike.tenant_id'',true) AND owner_user_id=current_setting(''yike.user_id'',true))',item);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid=item::regclass AND tgname='candidate_immutable') THEN
            EXECUTE format('CREATE TRIGGER candidate_immutable BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION pilot_candidate_immutable()',item);
        END IF;
    END LOOP;
END $$;
