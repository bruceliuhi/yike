-- STOP acknowledges an already cancelled native execution; no new capabilities.
ALTER TABLE pilot_execution_operations DROP CONSTRAINT IF EXISTS pilot_execution_operations_operation_check;
ALTER TABLE pilot_execution_operations ADD CONSTRAINT pilot_execution_operations_operation_check
    CHECK (operation IN ('START','CLAIM','RENEW','CANCEL','FINISH','STOP'));
