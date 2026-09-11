CREATE TABLE IF NOT EXISTS pilot_material_profile_references (
 tenant_id TEXT NOT NULL, reference_id UUID NOT NULL, target_profile_version_id TEXT NOT NULL,
 field_name TEXT NOT NULL CHECK(field_name IN('service','customer','regions','preference','exclusions')),
 source_owner_user_id TEXT NOT NULL, source_profile_version_id TEXT NOT NULL, material_id TEXT NOT NULL,
 material_version INTEGER NOT NULL CHECK(material_version>0), extraction_id TEXT NOT NULL,
 adopted_value_sha256 TEXT NOT NULL CHECK(adopted_value_sha256~'^[a-f0-9]{64}$'), valid BOOLEAN NOT NULL DEFAULT TRUE,
 invalidated_at TIMESTAMPTZ, invalidation_reason TEXT,
 PRIMARY KEY(tenant_id,reference_id), UNIQUE(tenant_id,target_profile_version_id,field_name),
 FOREIGN KEY(tenant_id,target_profile_version_id) REFERENCES business_profile_versions(tenant_id,profile_version_id),
 FOREIGN KEY(tenant_id,source_owner_user_id,source_profile_version_id,material_id,material_version)
   REFERENCES pilot_material_revisions(tenant_id,owner_user_id,profile_version_id,material_id,material_version)
);
ALTER TABLE pilot_material_profile_references ENABLE ROW LEVEL SECURITY;
ALTER TABLE pilot_material_profile_references FORCE ROW LEVEL SECURITY;
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_policies WHERE tablename='pilot_material_profile_references' AND policyname='pilot_material_profile_reference_tenant_select') THEN
  CREATE POLICY pilot_material_profile_reference_tenant_select ON pilot_material_profile_references FOR SELECT
   USING(tenant_id=current_setting('yike.tenant_id',true));
  CREATE POLICY pilot_material_profile_reference_insert ON pilot_material_profile_references FOR INSERT
   WITH CHECK(tenant_id=current_setting('yike.tenant_id',true));
  CREATE POLICY pilot_material_profile_reference_owner_invalidate ON pilot_material_profile_references FOR UPDATE
   USING(tenant_id=current_setting('yike.tenant_id',true) AND source_owner_user_id=current_setting('yike.user_id',true))
   WITH CHECK(tenant_id=current_setting('yike.tenant_id',true) AND source_owner_user_id=current_setting('yike.user_id',true)
              AND valid=FALSE AND invalidated_at IS NOT NULL);
 END IF;
END $$;
CREATE OR REPLACE FUNCTION pilot_material_reference_provenance_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.tenant_id<>OLD.tenant_id OR NEW.reference_id<>OLD.reference_id
 OR NEW.target_profile_version_id<>OLD.target_profile_version_id OR NEW.field_name<>OLD.field_name
 OR NEW.source_owner_user_id<>OLD.source_owner_user_id OR NEW.source_profile_version_id<>OLD.source_profile_version_id
 OR NEW.material_id<>OLD.material_id OR NEW.material_version<>OLD.material_version
 OR NEW.extraction_id<>OLD.extraction_id OR NEW.adopted_value_sha256<>OLD.adopted_value_sha256
 OR OLD.valid=FALSE OR NEW.valid<>FALSE THEN RAISE EXCEPTION 'material reference provenance is immutable'; END IF;
 RETURN NEW;
END $$;
DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname='pilot_material_reference_provenance_immutable') THEN
 CREATE TRIGGER pilot_material_reference_provenance_immutable BEFORE UPDATE ON pilot_material_profile_references
  FOR EACH ROW EXECUTE FUNCTION pilot_material_reference_provenance_immutable();
END IF; END $$;
ALTER TABLE pilot_material_impact_tokens ADD COLUMN IF NOT EXISTS reference_snapshot_sha256 TEXT;
ALTER TABLE pilot_material_impact_tokens DROP CONSTRAINT IF EXISTS pilot_material_impact_tokens_reference_snapshot_check;
ALTER TABLE pilot_material_impact_tokens ADD CONSTRAINT pilot_material_impact_tokens_reference_snapshot_check
 CHECK(reference_snapshot_sha256 IS NULL OR reference_snapshot_sha256~'^[a-f0-9]{64}$');
