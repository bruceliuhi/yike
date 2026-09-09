CREATE TABLE IF NOT EXISTS pilot_device_registrations (
    tenant_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    request_id TEXT NOT NULL CHECK (
        request_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    ),
    device_id TEXT NOT NULL CHECK (
        device_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    ),
    device_label TEXT NOT NULL CHECK (
        device_label=btrim(device_label) AND char_length(device_label) BETWEEN 1 AND 128
    ),
    registered_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, owner_user_id, request_id),
    UNIQUE (tenant_id, owner_user_id, device_id),
    FOREIGN KEY (tenant_id, owner_user_id, device_id)
        REFERENCES pilot_devices(tenant_id, owner_user_id, device_id)
);

ALTER TABLE pilot_device_registrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_device_registrations FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname=current_schema()
        AND tablename='pilot_device_registrations'
        AND policyname='device_registration_owner_select'
    ) THEN
        CREATE POLICY device_registration_owner_select
            ON pilot_device_registrations FOR SELECT
            USING (
                tenant_id=current_setting('yike.tenant_id',true)
                AND owner_user_id=current_setting('yike.user_id',true)
            );
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE schemaname=current_schema()
        AND tablename='pilot_device_registrations'
        AND policyname='device_registration_owner_insert'
    ) THEN
        CREATE POLICY device_registration_owner_insert
            ON pilot_device_registrations FOR INSERT
            WITH CHECK (
                tenant_id=current_setting('yike.tenant_id',true)
                AND owner_user_id=current_setting('yike.user_id',true)
            );
    END IF;
END $$;
-- No UPDATE/DELETE policy or runtime grant. Registration receipts are immutable.
