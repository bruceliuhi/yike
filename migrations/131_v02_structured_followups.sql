CREATE TABLE IF NOT EXISTS pilot_structured_followup_revisions (
 tenant_id TEXT NOT NULL, owner_user_id TEXT NOT NULL, record_id TEXT NOT NULL,
 revision INTEGER NOT NULL CHECK(revision>0), opportunity_id TEXT NOT NULL, profile_version_id TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN('CONTACTED','REPLIED','MEETING','QUOTED','LOST','WON')),
 note TEXT NOT NULL CHECK(length(note) BETWEEN 1 AND 500), occurred_at TIMESTAMPTZ,
 next_step TEXT NOT NULL CHECK(length(next_step)<=500), next_followup_at TIMESTAMPTZ,
 assignee_user_id TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN('ACTIVE','CORRECTED','VOID')),
 corrects_id TEXT, reason TEXT CHECK(reason IS NULL OR length(reason) BETWEEN 1 AND 500),
 created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(), recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,owner_user_id,record_id,revision),
 FOREIGN KEY(tenant_id,owner_user_id) REFERENCES pilot_users(tenant_id,user_id),
 FOREIGN KEY(tenant_id,assignee_user_id) REFERENCES pilot_users(tenant_id,user_id),
 FOREIGN KEY(tenant_id,opportunity_id) REFERENCES pilot_opportunities(tenant_id,opportunity_id),
 FOREIGN KEY(tenant_id,profile_version_id) REFERENCES business_profile_versions(tenant_id,profile_version_id)
);
CREATE TABLE IF NOT EXISTS pilot_followup_reply_reads (
 tenant_id TEXT NOT NULL, owner_user_id TEXT NOT NULL, reply_event_id TEXT NOT NULL,
 revision INTEGER NOT NULL CHECK(revision>0), read BOOLEAN NOT NULL, recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(tenant_id,owner_user_id,reply_event_id,revision),
 FOREIGN KEY(tenant_id,owner_user_id) REFERENCES pilot_users(tenant_id,user_id)
);
CREATE TABLE IF NOT EXISTS pilot_followup_operations (
 tenant_id TEXT NOT NULL, owner_user_id TEXT NOT NULL, request_id TEXT NOT NULL, request_sha256 TEXT NOT NULL CHECK(request_sha256~'^[a-f0-9]{64}$'),
 binding JSONB NOT NULL CHECK(jsonb_typeof(binding)='object'), receipt JSONB NOT NULL CHECK(jsonb_typeof(receipt)='object'),
 created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(), PRIMARY KEY(tenant_id,owner_user_id,request_id),
 FOREIGN KEY(tenant_id,owner_user_id) REFERENCES pilot_users(tenant_id,user_id)
);
DO $$ DECLARE item TEXT; BEGIN FOREACH item IN ARRAY ARRAY['pilot_structured_followup_revisions','pilot_followup_reply_reads','pilot_followup_operations'] LOOP
 EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',item); EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',item);
 IF NOT EXISTS(SELECT 1 FROM pg_policies WHERE tablename=item AND policyname=item||'_owner') THEN
  EXECUTE format('CREATE POLICY %I ON %I USING (tenant_id=current_setting(''yike.tenant_id'',true) AND owner_user_id=current_setting(''yike.user_id'',true)) WITH CHECK (tenant_id=current_setting(''yike.tenant_id'',true) AND owner_user_id=current_setting(''yike.user_id'',true))',item||'_owner',item);
 END IF; END LOOP; END $$;
CREATE OR REPLACE FUNCTION yike_followup_members() RETURNS TABLE(user_id TEXT)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
 SELECT u.user_id FROM public.pilot_users u
 WHERE u.tenant_id=current_setting('yike.tenant_id',true)
   AND current_setting('yike.user_id',true)<>''
   AND EXISTS(SELECT 1 FROM public.pilot_users me WHERE me.tenant_id=u.tenant_id AND me.user_id=current_setting('yike.user_id',true))
$$;
REVOKE ALL ON FUNCTION yike_followup_members() FROM PUBLIC;
CREATE OR REPLACE FUNCTION pilot_structured_followup_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'structured followup is immutable'; END $$;
DO $$ DECLARE item TEXT; BEGIN FOREACH item IN ARRAY ARRAY['pilot_structured_followup_revisions','pilot_followup_reply_reads','pilot_followup_operations'] LOOP
 IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid=item::regclass AND tgname=item||'_immutable') THEN EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION pilot_structured_followup_immutable()',item||'_immutable',item); END IF;
 END LOOP; END $$;
