-- VERIFY records an authenticated owner client's bound local observation.
-- It is not server-side platform proof or authorization to execute a task.
ALTER TABLE pilot_connection_operations
    DROP CONSTRAINT IF EXISTS pilot_connection_operations_action_check;
ALTER TABLE pilot_connection_operations
    ADD CONSTRAINT pilot_connection_operations_action_check
    CHECK (action IN ('REGISTER','DISCONNECT','VERIFY'));
