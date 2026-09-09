-- Tenant-shared, immutable public evidence retained at the first human inclusion.
CREATE TABLE IF NOT EXISTS pilot_opportunity_evidence (
    tenant_id TEXT NOT NULL,
    opportunity_id TEXT NOT NULL,
    included_by_user_id TEXT NOT NULL,
    include_request_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    payload_sha256 TEXT NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    PRIMARY KEY (tenant_id, opportunity_id),
    FOREIGN KEY (tenant_id, opportunity_id)
        REFERENCES pilot_opportunities(tenant_id, opportunity_id) ON DELETE CASCADE,
    CHECK ((jsonb_typeof(payload)='object'
        AND payload->>'schema_version'='opportunity-source-evidence-v1'
        AND payload->>'opportunity_id'=opportunity_id) IS TRUE)
);

CREATE OR REPLACE FUNCTION pilot_opportunity_evidence_binding() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pilot_candidate_reviews review
        JOIN pilot_candidate_review_requests request
          USING (tenant_id, owner_user_id, request_id)
        JOIN pilot_opportunities opportunity
          ON opportunity.tenant_id=review.tenant_id
         AND opportunity.opportunity_id=review.opportunity_id
        WHERE review.tenant_id=NEW.tenant_id
          AND review.owner_user_id=NEW.included_by_user_id
          AND review.request_id=NEW.include_request_id
          AND review.opportunity_id=NEW.opportunity_id
          AND request.action='INCLUDE'
          AND request.status='SUCCEEDED'
          AND request.result#>>'{receipt,outcome}'='IMPORTED'
          AND review.assessment_id::text=NEW.payload#>>'{assessment,id}'
          AND request.payload->>'assessmentId'=NEW.payload#>>'{assessment,id}'
          AND request.payload->>'profileId'=NEW.payload#>>'{assessment,profile_version_id}'
          AND request.payload->'profileVersion'=NEW.payload#>'{assessment,profile_version}'
          AND request.payload->>'sourceVersionId'=NEW.payload#>>'{source,version_id}'
          AND opportunity.profile_version_id=NEW.payload#>>'{assessment,profile_version_id}'
    ) THEN
        RAISE EXCEPTION 'opportunity evidence binding mismatch';
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION pilot_opportunity_evidence_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'opportunity evidence is immutable';
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid='pilot_opportunity_evidence'::regclass
          AND tgname='opportunity_evidence_binding'
    ) THEN
        CREATE TRIGGER opportunity_evidence_binding
            BEFORE INSERT ON pilot_opportunity_evidence
            FOR EACH ROW EXECUTE FUNCTION pilot_opportunity_evidence_binding();
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid='pilot_opportunity_evidence'::regclass
          AND tgname='opportunity_evidence_immutable'
    ) THEN
        CREATE TRIGGER opportunity_evidence_immutable
            BEFORE UPDATE ON pilot_opportunity_evidence
            FOR EACH ROW EXECUTE FUNCTION pilot_opportunity_evidence_immutable();
    END IF;
END $$;

ALTER TABLE pilot_opportunity_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_opportunity_evidence FORCE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname=current_schema()
          AND tablename='pilot_opportunity_evidence'
          AND policyname='opportunity_evidence_tenant_select'
    ) THEN
        CREATE POLICY opportunity_evidence_tenant_select
            ON pilot_opportunity_evidence FOR SELECT
            USING (tenant_id=current_setting('yike.tenant_id',true));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname=current_schema()
          AND tablename='pilot_opportunity_evidence'
          AND policyname='opportunity_evidence_includer_insert'
    ) THEN
        CREATE POLICY opportunity_evidence_includer_insert
            ON pilot_opportunity_evidence FOR INSERT
            WITH CHECK (
                tenant_id=current_setting('yike.tenant_id',true)
                AND included_by_user_id=current_setting('yike.user_id',true)
            );
    END IF;
END $$;
