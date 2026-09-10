-- Durable online binding and at-most-once monitor occurrence reservations.
CREATE TABLE IF NOT EXISTS pilot_monitor_bindings (
 tenant_id TEXT NOT NULL, owner_user_id TEXT NOT NULL, plan_id TEXT NOT NULL,
 plan_revision INTEGER NOT NULL CHECK(plan_revision BETWEEN 1 AND 2147483647),
 device_id TEXT NOT NULL, credential_version INTEGER NOT NULL CHECK(credential_version BETWEEN 1 AND 2147483647),
 targets JSONB NOT NULL CHECK(jsonb_typeof(targets)='array'),
 monitor_session_id TEXT NOT NULL CHECK(monitor_session_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
 last_seen_at TIMESTAMPTZ NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,owner_user_id,plan_id,plan_revision),
 FOREIGN KEY(tenant_id,owner_user_id,plan_id) REFERENCES pilot_monitor_plans(tenant_id,owner_user_id,plan_id),
 FOREIGN KEY(tenant_id,owner_user_id,device_id) REFERENCES pilot_devices(tenant_id,owner_user_id,device_id)
);
CREATE TABLE IF NOT EXISTS pilot_monitor_occurrences (
 tenant_id TEXT NOT NULL, owner_user_id TEXT NOT NULL,
 occurrence_id TEXT NOT NULL CHECK(occurrence_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
 plan_id TEXT NOT NULL, plan_revision INTEGER NOT NULL CHECK(plan_revision BETWEEN 1 AND 2147483647),
 scheduled_at TIMESTAMPTZ NOT NULL, expires_at TIMESTAMPTZ NOT NULL,
 device_id TEXT NOT NULL, request_id TEXT NOT NULL,
 start_request JSONB NOT NULL CHECK(jsonb_typeof(start_request)='object'),
 status TEXT NOT NULL CHECK(status IN ('RESERVED','STARTED','EXPIRED','CLOSED')),
 task_id TEXT, run_id TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,owner_user_id,occurrence_id),
 UNIQUE(tenant_id,owner_user_id,plan_id,scheduled_at),
 UNIQUE(tenant_id,owner_user_id,request_id),
 FOREIGN KEY(tenant_id,owner_user_id,plan_id,plan_revision) REFERENCES pilot_monitor_bindings(tenant_id,owner_user_id,plan_id,plan_revision),
 FOREIGN KEY(tenant_id,owner_user_id,task_id) REFERENCES pilot_collection_tasks(tenant_id,owner_user_id,task_id),
 FOREIGN KEY(tenant_id,owner_user_id,task_id,run_id) REFERENCES pilot_collection_runs(tenant_id,owner_user_id,task_id,run_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS pilot_monitor_one_pending
 ON pilot_monitor_occurrences(tenant_id,owner_user_id,plan_id) WHERE status IN ('RESERVED','STARTED');
DO $$ DECLARE item TEXT; BEGIN
 FOREACH item IN ARRAY ARRAY['pilot_monitor_bindings','pilot_monitor_occurrences'] LOOP
  EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',item);
  EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',item);
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE schemaname=current_schema() AND tablename=item AND policyname=item||'_owner_all') THEN
   EXECUTE format('CREATE POLICY %I ON %I FOR ALL USING (tenant_id=current_setting(''yike.tenant_id'',true) AND owner_user_id=current_setting(''yike.user_id'',true)) WITH CHECK (tenant_id=current_setting(''yike.tenant_id'',true) AND owner_user_id=current_setting(''yike.user_id'',true))',item||'_owner_all',item);
  END IF;
 END LOOP;
END $$;
CREATE OR REPLACE FUNCTION pilot_monitor_binding_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF ROW(NEW.tenant_id,NEW.owner_user_id,NEW.plan_id,NEW.plan_revision,NEW.device_id,NEW.credential_version,NEW.targets,NEW.created_at)
    IS DISTINCT FROM ROW(OLD.tenant_id,OLD.owner_user_id,OLD.plan_id,OLD.plan_revision,OLD.device_id,OLD.credential_version,OLD.targets,OLD.created_at)
 THEN RAISE EXCEPTION 'monitor binding immutable'; END IF; RETURN NEW; END $$;
DROP TRIGGER IF EXISTS pilot_monitor_binding_guard ON pilot_monitor_bindings;
CREATE TRIGGER pilot_monitor_binding_guard BEFORE UPDATE OR DELETE ON pilot_monitor_bindings FOR EACH ROW EXECUTE FUNCTION pilot_monitor_binding_guard();
CREATE OR REPLACE FUNCTION pilot_monitor_occurrence_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF ROW(NEW.tenant_id,NEW.owner_user_id,NEW.occurrence_id,NEW.plan_id,NEW.plan_revision,NEW.scheduled_at,NEW.expires_at,NEW.device_id,NEW.request_id,NEW.start_request,NEW.created_at)
    IS DISTINCT FROM ROW(OLD.tenant_id,OLD.owner_user_id,OLD.occurrence_id,OLD.plan_id,OLD.plan_revision,OLD.scheduled_at,OLD.expires_at,OLD.device_id,OLD.request_id,OLD.start_request,OLD.created_at)
 THEN RAISE EXCEPTION 'monitor occurrence immutable'; END IF; RETURN NEW; END $$;
DROP TRIGGER IF EXISTS pilot_monitor_occurrence_guard ON pilot_monitor_occurrences;
CREATE TRIGGER pilot_monitor_occurrence_guard BEFORE UPDATE OR DELETE ON pilot_monitor_occurrences FOR EACH ROW EXECUTE FUNCTION pilot_monitor_occurrence_guard();
