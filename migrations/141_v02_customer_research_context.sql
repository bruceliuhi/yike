-- Immutable context for one authenticated signed research task. No effect grant.
CREATE TABLE IF NOT EXISTS pilot_customer_research_contexts (
 tenant_id TEXT NOT NULL, owner_user_id TEXT NOT NULL,
 task_id TEXT NOT NULL, run_id TEXT NOT NULL, reservation_id TEXT NOT NULL,
 profile_version_id TEXT NOT NULL, strategy_version_id TEXT NOT NULL,
 profile_sha256 TEXT NOT NULL CHECK(profile_sha256 ~ '^[a-f0-9]{64}$'),
 configuration_sha256 TEXT NOT NULL CHECK(configuration_sha256 ~ '^[a-f0-9]{64}$'),
 -- Compiler caps canonical JSON at 512 KiB; JSONB rendering adds whitespace.
 context JSONB NOT NULL CHECK(jsonb_typeof(context)='object' AND octet_length(context::text)<=600000),
 binding JSONB NOT NULL CHECK(jsonb_typeof(binding)='object' AND octet_length(binding::text)<=4096),
 created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,owner_user_id,task_id,run_id),
 FOREIGN KEY(tenant_id,owner_user_id,task_id,run_id)
  REFERENCES pilot_collection_runs(tenant_id,owner_user_id,task_id,run_id) ON DELETE CASCADE,
 FOREIGN KEY(tenant_id,owner_user_id,reservation_id)
  REFERENCES pilot_research_reservations(tenant_id,owner_user_id,reservation_id) ON DELETE CASCADE,
 FOREIGN KEY(tenant_id,profile_version_id)
  REFERENCES business_profile_versions(tenant_id,profile_version_id),
 FOREIGN KEY(tenant_id,owner_user_id,strategy_version_id)
  REFERENCES pilot_research_strategy_versions(tenant_id,owner_user_id,strategy_version_id),
 CHECK ((context->>'schema_version'='research-context-v2'
  AND context->>'profile_version_id'=profile_version_id
  AND context->>'strategy_version_id'=strategy_version_id
  AND context->>'profile_sha256'=profile_sha256
  AND binding->>'schema_version'='research-context-v2'
  AND binding->>'profile_version_id'=profile_version_id
  AND binding->>'strategy_version_id'=strategy_version_id
  AND binding->>'profile_sha256'=profile_sha256
  AND binding->>'configuration_sha256'=configuration_sha256) IS TRUE)
);
ALTER TABLE pilot_customer_research_contexts ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_customer_research_contexts FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_policies WHERE schemaname=current_schema()
  AND tablename='pilot_customer_research_contexts' AND policyname='customer_context_owner_select') THEN
  CREATE POLICY customer_context_owner_select ON pilot_customer_research_contexts FOR SELECT
   USING(tenant_id=current_setting('yike.tenant_id',true) AND owner_user_id=current_setting('yike.user_id',true));
 END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_policies WHERE schemaname=current_schema()
  AND tablename='pilot_customer_research_contexts' AND policyname='customer_context_owner_insert') THEN
  CREATE POLICY customer_context_owner_insert ON pilot_customer_research_contexts FOR INSERT
   WITH CHECK(tenant_id=current_setting('yike.tenant_id',true) AND owner_user_id=current_setting('yike.user_id',true));
 END IF;
END $$;
CREATE OR REPLACE FUNCTION pilot_customer_research_context_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='UPDATE' THEN
  RAISE EXCEPTION USING ERRCODE='YT041', MESSAGE='customer_context_immutable';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM pilot_research_reservations r JOIN pilot_collection_tasks t
  ON t.tenant_id=r.tenant_id AND t.owner_user_id=r.owner_user_id AND t.task_id=r.task_id
  JOIN business_profile_versions p ON p.tenant_id=r.tenant_id AND p.profile_version_id=r.profile_version_id
  WHERE r.tenant_id=NEW.tenant_id AND r.owner_user_id=NEW.owner_user_id
   AND r.reservation_id=NEW.reservation_id AND r.task_id=NEW.task_id AND r.run_id=NEW.run_id
   AND r.profile_version_id=NEW.profile_version_id AND r.strategy_version_id=NEW.strategy_version_id
   AND r.configuration_sha256=NEW.configuration_sha256
   AND p.content_sha256=NEW.profile_sha256 AND p.payload->>'description'=NEW.context->>'seller_description'
   AND t.configuration_snapshot=NEW.context->'strategy_snapshot'
   AND t.created_at=(NEW.context->>'reference_time')::timestamptz) THEN
  RAISE EXCEPTION USING ERRCODE='YT041', MESSAGE='customer_context_binding_invalid';
 END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS pilot_customer_research_context_guard ON pilot_customer_research_contexts;
CREATE TRIGGER pilot_customer_research_context_guard BEFORE INSERT OR UPDATE ON pilot_customer_research_contexts
 FOR EACH ROW EXECUTE FUNCTION pilot_customer_research_context_guard();
