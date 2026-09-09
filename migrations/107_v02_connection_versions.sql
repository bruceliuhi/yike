ALTER TABLE pilot_platform_connections ADD COLUMN IF NOT EXISTS connection_version INTEGER NOT NULL DEFAULT 1
    CHECK (connection_version BETWEEN 1 AND 2147483647);

CREATE OR REPLACE FUNCTION pilot_connection_version_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE changed BOOLEAN;
BEGIN
    IF TG_OP='INSERT' THEN
        IF NEW.connection_version IS DISTINCT FROM 1 THEN
            RAISE EXCEPTION USING ERRCODE='YC002', MESSAGE='connection_version_conflict';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.connection_version IS NULL OR
       (NEW.connection_version::bigint <> OLD.connection_version::bigint AND
        NEW.connection_version::bigint <> OLD.connection_version::bigint + 1) THEN
        RAISE EXCEPTION USING ERRCODE='YC002', MESSAGE='connection_version_conflict';
    END IF;
    changed := ROW(NEW.device_id,NEW.platform,NEW.account_public_id,NEW.session_ref,NEW.status)
        IS DISTINCT FROM ROW(OLD.device_id,OLD.platform,OLD.account_public_id,OLD.session_ref,OLD.status)
        OR NEW.connection_version <> OLD.connection_version;
    IF changed THEN
        IF OLD.connection_version=2147483647 THEN
            RAISE EXCEPTION USING ERRCODE='YC001', MESSAGE='connection_version_exhausted';
        END IF;
        NEW.connection_version := OLD.connection_version + 1;
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS pilot_connection_version_guard ON pilot_platform_connections;
CREATE TRIGGER pilot_connection_version_guard BEFORE INSERT OR UPDATE ON pilot_platform_connections
    FOR EACH ROW EXECUTE FUNCTION pilot_connection_version_guard();

CREATE TABLE IF NOT EXISTS pilot_connection_operations (
    tenant_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    request_id TEXT NOT NULL CHECK (request_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
    requested_device_id TEXT NOT NULL CHECK (requested_device_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
    authorized_device_id TEXT,
    request_sha256 TEXT NOT NULL CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
    action TEXT NOT NULL CHECK (action IN ('REGISTER','DISCONNECT')),
    state TEXT NOT NULL CHECK (state IN ('SUCCEEDED','REJECTED')),
    connection_id TEXT,
    connection_version INTEGER CHECK (connection_version BETWEEN 1 AND 2147483647),
    connection_status TEXT CHECK (connection_status IN ('UNVERIFIED','CONNECTED','EXPIRED','DISCONNECTED')),
    error_code TEXT CHECK (error_code IN ('device_unavailable','connection_unavailable','connection_version_conflict','connection_version_exhausted')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, owner_user_id, request_id),
    FOREIGN KEY (tenant_id, owner_user_id) REFERENCES pilot_users(tenant_id,user_id),
    FOREIGN KEY (tenant_id, owner_user_id, authorized_device_id)
        REFERENCES pilot_devices(tenant_id,owner_user_id,device_id),
    CHECK (authorized_device_id IS NULL OR authorized_device_id=requested_device_id),
    CHECK (authorized_device_id IS NOT NULL OR
        (state='REJECTED' AND error_code='device_unavailable' AND connection_id IS NULL
         AND connection_version IS NULL AND connection_status IS NULL)),
    CHECK ((state='SUCCEEDED' AND error_code IS NULL AND connection_id IS NOT NULL
         AND connection_version IS NOT NULL AND connection_status IS NOT NULL)
        OR (state='REJECTED' AND error_code IS NOT NULL)),
    CHECK ((connection_id IS NULL AND connection_version IS NULL AND connection_status IS NULL)
        OR (connection_id IS NOT NULL AND connection_version IS NOT NULL AND connection_status IS NOT NULL))
);
ALTER TABLE pilot_connection_operations ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_connection_operations FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=current_schema()
        AND tablename='pilot_connection_operations' AND policyname='connection_owner_select') THEN
        CREATE POLICY connection_owner_select ON pilot_connection_operations FOR SELECT USING
            (tenant_id=current_setting('yike.tenant_id',true) AND owner_user_id=current_setting('yike.user_id',true));
        CREATE POLICY connection_owner_insert ON pilot_connection_operations FOR INSERT WITH CHECK
            (tenant_id=current_setting('yike.tenant_id',true) AND owner_user_id=current_setting('yike.user_id',true));
    END IF;
END $$;
-- Immutable application receipts: no UPDATE/DELETE policy or runtime grants.
