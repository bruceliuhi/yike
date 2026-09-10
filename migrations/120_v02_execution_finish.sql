-- Add terminal success to the existing execution protocol only.
ALTER TABLE pilot_collection_tasks DROP CONSTRAINT IF EXISTS pilot_collection_tasks_status_check;
ALTER TABLE pilot_collection_tasks ADD CONSTRAINT pilot_collection_tasks_status_check
    CHECK (status IN ('PENDING','RUNNING','CANCELLING','CANCELED','SUCCEEDED'));
ALTER TABLE pilot_collection_runs DROP CONSTRAINT IF EXISTS pilot_collection_runs_status_check;
ALTER TABLE pilot_collection_runs ADD CONSTRAINT pilot_collection_runs_status_check
    CHECK (status IN ('PENDING','RUNNING','CANCELLING','CANCELED','SUCCEEDED'));
ALTER TABLE pilot_collection_platform_runs DROP CONSTRAINT IF EXISTS pilot_collection_platform_runs_status_check;
ALTER TABLE pilot_collection_platform_runs ADD CONSTRAINT pilot_collection_platform_runs_status_check
    CHECK (status IN ('PENDING','RUNNING','CANCELLING','CANCELED','SUCCEEDED'));
ALTER TABLE pilot_execution_operations DROP CONSTRAINT IF EXISTS pilot_execution_operations_operation_check;
ALTER TABLE pilot_execution_operations ADD CONSTRAINT pilot_execution_operations_operation_check
    CHECK (operation IN ('START','CLAIM','RENEW','CANCEL','FINISH'));
