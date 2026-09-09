-- Private decisions, immutable evidence and bounded paid-call reservations.
CREATE TABLE IF NOT EXISTS pilot_candidate_review_requests (
 tenant_id TEXT NOT NULL, owner_user_id TEXT NOT NULL, request_id TEXT NOT NULL,
 candidate_id UUID NOT NULL, fingerprint TEXT NOT NULL CHECK(fingerprint ~ '^[0-9a-f]{64}$'),
 action TEXT NOT NULL CHECK(action IN ('ASSESS','VERIFY_SOURCE','INCLUDE','EXCLUDE')),
 binding_hash TEXT NOT NULL, snapshot_key TEXT, invocation_id TEXT,
 attempt INTEGER NOT NULL DEFAULT 0 CHECK(attempt BETWEEN 0 AND 3),
 status TEXT NOT NULL CHECK(status IN ('PROCESSING','SUCCEEDED','FAILED','UNKNOWN')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(), deadline_at TIMESTAMPTZ,
 payload JSONB NOT NULL, snapshot JSONB NOT NULL, result JSONB NOT NULL,
 PRIMARY KEY(tenant_id,owner_user_id,request_id),
 UNIQUE(tenant_id,owner_user_id,request_id,binding_hash),
 FOREIGN KEY(tenant_id,owner_user_id,candidate_id) REFERENCES pilot_candidate_projections(tenant_id,owner_user_id,candidate_id),
 FOREIGN KEY(tenant_id,owner_user_id,invocation_id) REFERENCES pilot_candidate_review_requests(tenant_id,owner_user_id,request_id),
 CHECK ((action='ASSESS')=(snapshot_key IS NOT NULL)),
 CHECK ((attempt>0)=(action='ASSESS' AND invocation_id IS NULL)),
 CHECK ((deadline_at IS NOT NULL)=(attempt>0)),
 CHECK (deadline_at IS NULL OR deadline_at=created_at+interval '90 seconds')
);
CREATE INDEX IF NOT EXISTS candidate_review_snapshot ON pilot_candidate_review_requests(tenant_id,owner_user_id,snapshot_key,attempt DESC) WHERE attempt>0;
CREATE TABLE IF NOT EXISTS pilot_candidate_assessments (
 tenant_id TEXT NOT NULL, owner_user_id TEXT NOT NULL, assessment_id UUID NOT NULL,
 request_id TEXT NOT NULL, binding_hash TEXT NOT NULL, content JSONB NOT NULL,
 PRIMARY KEY(tenant_id,owner_user_id,assessment_id),
 UNIQUE(tenant_id,owner_user_id,assessment_id,binding_hash),
 UNIQUE(tenant_id,owner_user_id,request_id),
 FOREIGN KEY(tenant_id,owner_user_id,request_id,binding_hash) REFERENCES pilot_candidate_review_requests(tenant_id,owner_user_id,request_id,binding_hash)
);
CREATE TABLE IF NOT EXISTS pilot_candidate_source_verifications (
 tenant_id TEXT NOT NULL, owner_user_id TEXT NOT NULL, verification_id UUID NOT NULL,
 request_id TEXT NOT NULL, binding_hash TEXT NOT NULL,
 checked_at TIMESTAMPTZ NOT NULL, receipt JSONB NOT NULL,
 PRIMARY KEY(tenant_id,owner_user_id,verification_id),
 UNIQUE(tenant_id,owner_user_id,verification_id,binding_hash),
 UNIQUE(tenant_id,owner_user_id,request_id),
 FOREIGN KEY(tenant_id,owner_user_id,request_id,binding_hash) REFERENCES pilot_candidate_review_requests(tenant_id,owner_user_id,request_id,binding_hash)
);
CREATE TABLE IF NOT EXISTS pilot_candidate_reviews (
 tenant_id TEXT NOT NULL, owner_user_id TEXT NOT NULL, request_id TEXT NOT NULL,
 binding_hash TEXT NOT NULL, assessment_id UUID NOT NULL, verification_id UUID,
 opportunity_id TEXT, result JSONB NOT NULL,
 PRIMARY KEY(tenant_id,owner_user_id,request_id),
 FOREIGN KEY(tenant_id,owner_user_id,request_id,binding_hash) REFERENCES pilot_candidate_review_requests(tenant_id,owner_user_id,request_id,binding_hash),
 FOREIGN KEY(tenant_id,owner_user_id,assessment_id,binding_hash) REFERENCES pilot_candidate_assessments(tenant_id,owner_user_id,assessment_id,binding_hash),
 FOREIGN KEY(tenant_id,owner_user_id,verification_id,binding_hash) REFERENCES pilot_candidate_source_verifications(tenant_id,owner_user_id,verification_id,binding_hash),
 FOREIGN KEY(tenant_id,opportunity_id) REFERENCES pilot_opportunities(tenant_id,opportunity_id)
);
CREATE TABLE IF NOT EXISTS pilot_candidate_call_quota (
 tenant_id TEXT NOT NULL REFERENCES pilot_tenants(tenant_id), reservation_day DATE NOT NULL,
 reserved_calls INTEGER NOT NULL CHECK(reserved_calls>=0), PRIMARY KEY(tenant_id,reservation_day)
);
CREATE OR REPLACE FUNCTION pilot_candidate_review_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_TABLE_NAME<>'pilot_candidate_review_requests' THEN
   RAISE EXCEPTION 'candidate review evidence is immutable';
 END IF;
 IF OLD.status<>'PROCESSING'
    OR OLD.invocation_id IS NOT NULL OR NEW.status NOT IN ('SUCCEEDED','FAILED','UNKNOWN')
    OR (to_jsonb(OLD)-ARRAY['status','result']) IS DISTINCT FROM (to_jsonb(NEW)-ARRAY['status','result']) THEN
   RAISE EXCEPTION 'candidate review evidence is immutable';
 END IF;
 RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION pilot_candidate_review_alias() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.invocation_id IS NOT NULL AND NOT EXISTS(
   SELECT 1 FROM pilot_candidate_review_requests r WHERE r.tenant_id=NEW.tenant_id
    AND r.owner_user_id=NEW.owner_user_id AND r.request_id=NEW.invocation_id
    AND r.invocation_id IS NULL AND r.attempt>0 AND r.snapshot_key=NEW.snapshot_key
    AND r.binding_hash=NEW.binding_hash) THEN RAISE EXCEPTION 'invalid assessment alias'; END IF;
 RETURN NEW;
END $$;
DO $$ DECLARE item TEXT; BEGIN
 FOREACH item IN ARRAY ARRAY['pilot_candidate_review_requests','pilot_candidate_assessments','pilot_candidate_source_verifications','pilot_candidate_reviews'] LOOP
  EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',item);
  EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',item);
  IF NOT EXISTS(SELECT 1 FROM pg_policies WHERE tablename=item AND policyname='candidate_review_owner') THEN
   EXECUTE format('CREATE POLICY candidate_review_owner ON %I USING(tenant_id=current_setting(''yike.tenant_id'',true) AND owner_user_id=current_setting(''yike.user_id'',true)) WITH CHECK(tenant_id=current_setting(''yike.tenant_id'',true) AND owner_user_id=current_setting(''yike.user_id'',true))',item);
  END IF;
  IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid=item::regclass AND tgname='candidate_review_immutable') THEN
   EXECUTE format('CREATE TRIGGER candidate_review_immutable BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION pilot_candidate_review_immutable()',item);
  END IF;
 END LOOP;
 IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid='pilot_candidate_review_requests'::regclass AND tgname='candidate_review_alias') THEN
  CREATE TRIGGER candidate_review_alias BEFORE INSERT ON pilot_candidate_review_requests FOR EACH ROW EXECUTE FUNCTION pilot_candidate_review_alias();
 END IF;
END $$;
ALTER TABLE pilot_candidate_call_quota ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_candidate_call_quota FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_policies WHERE tablename='pilot_candidate_call_quota' AND policyname='candidate_quota_tenant') THEN
  CREATE POLICY candidate_quota_tenant ON pilot_candidate_call_quota USING(tenant_id=current_setting('yike.tenant_id',true)) WITH CHECK(tenant_id=current_setting('yike.tenant_id',true));
 END IF;
END $$;
