CREATE TABLE IF NOT EXISTS pilot_devices (
    device_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES pilot_tenants(tenant_id),
    device_label TEXT NOT NULL CHECK (length(trim(device_label)) BETWEEN 1 AND 128),
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'REVOKED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at TIMESTAMPTZ,
    UNIQUE (tenant_id, device_id)
);

CREATE TABLE IF NOT EXISTS pilot_platform_connections (
    connection_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    platform TEXT NOT NULL CHECK (platform IN ('XIAOHONGSHU', 'DOUYIN', 'BILIBILI', 'ZHIHU', 'PUBLIC_WEB')),
    account_public_id TEXT NOT NULL CHECK (length(trim(account_public_id)) BETWEEN 1 AND 256),
    session_ref TEXT NOT NULL CHECK (session_ref LIKE 'vault://%' AND length(session_ref) <= 512),
    status TEXT NOT NULL DEFAULT 'UNVERIFIED' CHECK (status IN ('UNVERIFIED', 'CONNECTED', 'DISCONNECTED', 'EXPIRED')),
    connected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    disconnected_at TIMESTAMPTZ,
    UNIQUE (tenant_id, connection_id),
    UNIQUE (tenant_id, device_id, connection_id),
    UNIQUE (tenant_id, device_id, platform, account_public_id),
    FOREIGN KEY (tenant_id, device_id) REFERENCES pilot_devices(tenant_id, device_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS pilot_tasks_tenant_task_id_key ON pilot_tasks(tenant_id, task_id);

CREATE TABLE IF NOT EXISTS pilot_execution_events (
    event_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    connection_id TEXT NOT NULL,
    task_id TEXT,
    execution_generation BIGINT NOT NULL CHECK (execution_generation > 0),
    event_type TEXT NOT NULL CHECK (event_type IN (
        'COLLECTION_STARTED', 'COLLECTION_PROGRESS', 'COLLECTION_SUCCEEDED',
        'COLLECTION_FAILED', 'COLLECTION_CANCELLED', 'CONNECTION_EXPIRED',
        'CONNECTION_REVOKED'
    )),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, event_id),
    FOREIGN KEY (tenant_id, device_id) REFERENCES pilot_devices(tenant_id, device_id),
    FOREIGN KEY (tenant_id, device_id, connection_id) REFERENCES pilot_platform_connections(tenant_id, device_id, connection_id),
    FOREIGN KEY (tenant_id, task_id) REFERENCES pilot_tasks(tenant_id, task_id)
);

ALTER TABLE pilot_devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_devices FORCE ROW LEVEL SECURITY;
ALTER TABLE pilot_platform_connections ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_platform_connections FORCE ROW LEVEL SECURITY;
ALTER TABLE pilot_execution_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_execution_events FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = current_schema() AND tablename = 'pilot_devices' AND policyname = 'pilot_tenant_scope') THEN
        CREATE POLICY pilot_tenant_scope ON pilot_devices USING (tenant_id = current_setting('yike.tenant_id', true)) WITH CHECK (tenant_id = current_setting('yike.tenant_id', true));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = current_schema() AND tablename = 'pilot_platform_connections' AND policyname = 'pilot_tenant_scope') THEN
        CREATE POLICY pilot_tenant_scope ON pilot_platform_connections USING (tenant_id = current_setting('yike.tenant_id', true)) WITH CHECK (tenant_id = current_setting('yike.tenant_id', true));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = current_schema() AND tablename = 'pilot_execution_events' AND policyname = 'pilot_tenant_scope') THEN
        CREATE POLICY pilot_tenant_scope ON pilot_execution_events USING (tenant_id = current_setting('yike.tenant_id', true)) WITH CHECK (tenant_id = current_setting('yike.tenant_id', true));
    END IF;
END $$;
