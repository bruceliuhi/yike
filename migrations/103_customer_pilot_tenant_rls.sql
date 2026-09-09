-- Tenant directory rows are never part of the customer request surface. Keep
-- them fail-closed for the application role; trusted provisioning uses the
-- separate admin/owner connection described in the runbook.
ALTER TABLE pilot_tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_tenants FORCE ROW LEVEL SECURITY;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname = current_schema() AND tablename = 'pilot_tenants' AND policyname = 'pilot_tenant_identity') THEN
        CREATE POLICY pilot_tenant_identity ON pilot_tenants
            USING (tenant_id = current_setting('yike.tenant_id', true))
            WITH CHECK (tenant_id = current_setting('yike.tenant_id', true));
    END IF;
END $$;
