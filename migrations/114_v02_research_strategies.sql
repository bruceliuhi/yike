-- User-confirmed intent only. Source capability and execution budgets are separate.
CREATE TABLE IF NOT EXISTS pilot_research_strategy_drafts (
    tenant_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    draft_id TEXT NOT NULL CHECK (draft_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
    current_revision INTEGER NOT NULL CHECK (current_revision BETWEEN 1 AND 2147483647),
    current_version_id TEXT NOT NULL,
    PRIMARY KEY (tenant_id,owner_user_id,draft_id),
    FOREIGN KEY (tenant_id,owner_user_id) REFERENCES pilot_users(tenant_id,user_id)
);
CREATE TABLE IF NOT EXISTS pilot_research_strategy_versions (
    tenant_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    strategy_version_id TEXT NOT NULL CHECK (strategy_version_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
    draft_id TEXT NOT NULL,
    draft_revision INTEGER NOT NULL CHECK (draft_revision BETWEEN 1 AND 2147483647),
    profile_version_id TEXT NOT NULL,
    profile_sha256 TEXT NOT NULL CHECK (profile_sha256 ~ '^[0-9a-f]{64}$'),
    snapshot JSONB NOT NULL CHECK (jsonb_typeof(snapshot)='object'),
    configuration_sha256 TEXT NOT NULL CHECK (configuration_sha256 ~ '^[0-9a-f]{64}$'),
    state TEXT NOT NULL DEFAULT 'DRAFT' CHECK (state IN ('DRAFT','CONFIRMED','REVOKED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    confirmed_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id,owner_user_id,strategy_version_id),
    UNIQUE (tenant_id,owner_user_id,draft_id,draft_revision),
    UNIQUE (tenant_id,owner_user_id,draft_id,draft_revision,strategy_version_id),
    FOREIGN KEY (tenant_id,owner_user_id) REFERENCES pilot_users(tenant_id,user_id),
    FOREIGN KEY (tenant_id,owner_user_id,draft_id) REFERENCES pilot_research_strategy_drafts(tenant_id,owner_user_id,draft_id),
    FOREIGN KEY (tenant_id,profile_version_id) REFERENCES business_profile_versions(tenant_id,profile_version_id),
    CHECK ((state='DRAFT' AND confirmed_at IS NULL AND revoked_at IS NULL)
        OR (state='CONFIRMED' AND confirmed_at IS NOT NULL AND revoked_at IS NULL)
        OR (state='REVOKED' AND revoked_at IS NOT NULL))
);
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='pilot_research_strategy_drafts'::regclass
        AND conname='pilot_strategy_current_version_fk') THEN
        ALTER TABLE pilot_research_strategy_drafts ADD CONSTRAINT pilot_strategy_current_version_fk
            FOREIGN KEY (tenant_id,owner_user_id,draft_id,current_revision,current_version_id)
            REFERENCES pilot_research_strategy_versions(tenant_id,owner_user_id,draft_id,draft_revision,strategy_version_id)
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END $$;
CREATE TABLE IF NOT EXISTS pilot_research_strategy_operations (
    tenant_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    request_id TEXT NOT NULL CHECK (request_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
    operation TEXT NOT NULL CHECK (operation IN ('PREPARE','CONFIRM','REVOKE')),
    request_sha256 TEXT NOT NULL CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
    strategy_version_id TEXT NOT NULL,
    receipt JSONB NOT NULL CHECK (jsonb_typeof(receipt)='object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id,owner_user_id,request_id),
    FOREIGN KEY (tenant_id,owner_user_id) REFERENCES pilot_users(tenant_id,user_id),
    FOREIGN KEY (tenant_id,owner_user_id,strategy_version_id)
        REFERENCES pilot_research_strategy_versions(tenant_id,owner_user_id,strategy_version_id)
);

DO $$ DECLARE item TEXT; BEGIN
    FOREACH item IN ARRAY ARRAY['pilot_research_strategy_drafts','pilot_research_strategy_versions','pilot_research_strategy_operations'] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',item);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',item);
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=current_schema() AND tablename=item AND policyname='strategy_owner_select') THEN
            EXECUTE format('CREATE POLICY strategy_owner_select ON %I FOR SELECT USING (tenant_id=current_setting(''yike.tenant_id'',true) AND owner_user_id=current_setting(''yike.user_id'',true))',item);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=current_schema() AND tablename=item AND policyname='strategy_owner_insert') THEN
            EXECUTE format('CREATE POLICY strategy_owner_insert ON %I FOR INSERT WITH CHECK (tenant_id=current_setting(''yike.tenant_id'',true) AND owner_user_id=current_setting(''yike.user_id'',true))',item);
        END IF;
        IF item <> 'pilot_research_strategy_operations' AND NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=current_schema() AND tablename=item AND policyname='strategy_owner_update') THEN
            EXECUTE format('CREATE POLICY strategy_owner_update ON %I FOR UPDATE USING (tenant_id=current_setting(''yike.tenant_id'',true) AND owner_user_id=current_setting(''yike.user_id'',true)) WITH CHECK (tenant_id=current_setting(''yike.tenant_id'',true) AND owner_user_id=current_setting(''yike.user_id'',true))',item);
        END IF;
    END LOOP;
END $$;

CREATE OR REPLACE FUNCTION pilot_research_strategy_version_guard() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN
    IF TG_OP='INSERT' THEN
        IF NEW.state <> 'DRAFT' THEN
            RAISE EXCEPTION USING ERRCODE='YT001', MESSAGE='strategy_transition_invalid';
        END IF;
    ELSE
        IF ROW(NEW.tenant_id,NEW.owner_user_id,NEW.strategy_version_id,NEW.draft_id,NEW.draft_revision,
               NEW.profile_version_id,NEW.profile_sha256,NEW.snapshot,NEW.configuration_sha256,NEW.created_at)
            IS DISTINCT FROM ROW(OLD.tenant_id,OLD.owner_user_id,OLD.strategy_version_id,OLD.draft_id,OLD.draft_revision,
               OLD.profile_version_id,OLD.profile_sha256,OLD.snapshot,OLD.configuration_sha256,OLD.created_at)
            OR NOT ((OLD.state='DRAFT' AND NEW.state IN ('CONFIRMED','REVOKED'))
                OR (OLD.state='CONFIRMED' AND NEW.state='REVOKED')) THEN
            RAISE EXCEPTION USING ERRCODE='YT001', MESSAGE='strategy_transition_invalid';
        END IF;
        NEW.confirmed_at := CASE WHEN NEW.state='CONFIRMED' THEN clock_timestamp() ELSE OLD.confirmed_at END;
        NEW.revoked_at := CASE WHEN NEW.state='REVOKED' THEN clock_timestamp() ELSE NULL END;
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS pilot_research_strategy_version_guard ON pilot_research_strategy_versions;
CREATE TRIGGER pilot_research_strategy_version_guard BEFORE INSERT OR UPDATE ON pilot_research_strategy_versions
    FOR EACH ROW EXECUTE FUNCTION pilot_research_strategy_version_guard();

CREATE OR REPLACE FUNCTION pilot_research_strategy_draft_guard() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN
    IF ROW(NEW.tenant_id,NEW.owner_user_id,NEW.draft_id) IS DISTINCT FROM ROW(OLD.tenant_id,OLD.owner_user_id,OLD.draft_id)
        OR NEW.current_revision <= OLD.current_revision OR NEW.current_version_id=OLD.current_version_id THEN
        RAISE EXCEPTION USING ERRCODE='YT002', MESSAGE='strategy_draft_invalid';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS pilot_research_strategy_draft_guard ON pilot_research_strategy_drafts;
CREATE TRIGGER pilot_research_strategy_draft_guard BEFORE UPDATE ON pilot_research_strategy_drafts
    FOR EACH ROW EXECUTE FUNCTION pilot_research_strategy_draft_guard();

CREATE OR REPLACE FUNCTION pilot_research_strategy_operation_guard() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN
    RAISE EXCEPTION USING ERRCODE='YT003', MESSAGE='strategy_receipt_immutable';
END $$;
DROP TRIGGER IF EXISTS pilot_research_strategy_operation_guard ON pilot_research_strategy_operations;
CREATE TRIGGER pilot_research_strategy_operation_guard BEFORE UPDATE ON pilot_research_strategy_operations
    FOR EACH ROW EXECUTE FUNCTION pilot_research_strategy_operation_guard();
