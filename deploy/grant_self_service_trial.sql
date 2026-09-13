-- Applied by trusted migration connection, never by customer requests.
DO $$
DECLARE target_role text := nullif(current_setting('yike.app_role',true),'');
BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=target_role AND NOT rolsuper
                AND NOT rolbypassrls AND NOT rolcreaterole AND NOT rolcreatedb) THEN
  RAISE EXCEPTION 'restricted runtime role required';
 END IF;
 EXECUTE format('GRANT EXECUTE ON FUNCTION public.pilot_register_sms_trial(text,uuid,text) TO %I',target_role);
END $$;
