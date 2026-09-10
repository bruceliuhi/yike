-- Durable schedule intent only. No collection round or executor is connected.
CREATE TABLE IF NOT EXISTS pilot_monitor_plans (
 tenant_id TEXT NOT NULL, owner_user_id TEXT NOT NULL,
 plan_id TEXT NOT NULL CHECK(plan_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
 profile_version_id TEXT NOT NULL CHECK(profile_version_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
 strategy_version_id TEXT NOT NULL CHECK(strategy_version_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
 configuration_sha256 TEXT NOT NULL CHECK(configuration_sha256 ~ '^[a-f0-9]{64}$'),
 schedule JSONB NOT NULL CHECK(jsonb_typeof(schedule)='object'),
 state TEXT NOT NULL CHECK(state IN ('ACTIVE','PAUSED')),
 revision INTEGER NOT NULL CHECK(revision BETWEEN 1 AND 2147483647), next_due_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(), updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,owner_user_id,plan_id),
 UNIQUE(tenant_id,owner_user_id,strategy_version_id),
 FOREIGN KEY(tenant_id,owner_user_id) REFERENCES pilot_users(tenant_id,user_id),
 FOREIGN KEY(tenant_id,owner_user_id,strategy_version_id) REFERENCES pilot_research_strategy_versions(tenant_id,owner_user_id,strategy_version_id)
);
CREATE TABLE IF NOT EXISTS pilot_monitor_plan_operations (
 tenant_id TEXT NOT NULL, owner_user_id TEXT NOT NULL,
 request_id TEXT NOT NULL CHECK(request_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
 operation TEXT NOT NULL CHECK(operation IN ('CREATE','SET_STATE')),
 request_sha256 TEXT NOT NULL CHECK(request_sha256 ~ '^[a-f0-9]{64}$'), plan_id TEXT NOT NULL,
 receipt JSONB NOT NULL CHECK(jsonb_typeof(receipt)='object'), created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,owner_user_id,request_id),
 FOREIGN KEY(tenant_id,owner_user_id) REFERENCES pilot_users(tenant_id,user_id),
 FOREIGN KEY(tenant_id,owner_user_id,plan_id) REFERENCES pilot_monitor_plans(tenant_id,owner_user_id,plan_id)
);
DO $$ DECLARE item TEXT; BEGIN
 FOREACH item IN ARRAY ARRAY['pilot_monitor_plans','pilot_monitor_plan_operations'] LOOP
  EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',item);
  EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',item);
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=current_schema() AND tablename=item AND policyname=item||'_owner_all') THEN
   EXECUTE format('CREATE POLICY %I ON %I FOR ALL USING (tenant_id=current_setting(''yike.tenant_id'',true) AND owner_user_id=current_setting(''yike.user_id'',true)) WITH CHECK (tenant_id=current_setting(''yike.tenant_id'',true) AND owner_user_id=current_setting(''yike.user_id'',true))',item||'_owner_all',item);
  END IF;
 END LOOP;
END $$;
CREATE OR REPLACE FUNCTION pilot_monitor_operation_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'monitor receipt immutable'; END $$;
DROP TRIGGER IF EXISTS pilot_monitor_operation_immutable ON pilot_monitor_plan_operations;
CREATE TRIGGER pilot_monitor_operation_immutable BEFORE UPDATE OR DELETE ON pilot_monitor_plan_operations FOR EACH ROW EXECUTE FUNCTION pilot_monitor_operation_immutable();
