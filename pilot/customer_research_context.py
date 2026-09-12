"""Load immutable business context from signed tasks, not caller-supplied facts."""
import hashlib
import json

import psycopg

from pilot.execution_contract import ExecutionRuntimeError, canonical_uuid
from pilot.research_context import ResearchContextError, compile_research_context, project_research_context_v2
from pilot.research_history import load_research_history
from pilot.research_resources import ResearchResourceStore


class CustomerResearchContextStore:
    def __init__(self,runtime):
        self.runtime=runtime

    def load(self,claims,*,task_id,run_id):
        task_id,run_id=map(canonical_uuid,(task_id,run_id))
        try:
            with self.runtime.database.connect() as connection,connection.cursor() as cursor:
                tenant=self.runtime._active(cursor,claims)
                lock=int.from_bytes(hashlib.sha256((tenant+'\0'+claims.user_id+'\0'+task_id+'\0'+run_id).encode()).digest()[:4],
                                    'big',signed=True)
                cursor.execute('SELECT pg_advisory_xact_lock(14101,%s)',(lock,))
                cursor.execute('SELECT device_id,profile_version_id,strategy_version_id,configuration_sha256,configuration_snapshot '
                    'FROM pilot_collection_tasks WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s',
                    (tenant,claims.user_id,task_id))
                identity=cursor.fetchone()
                rows,targets=ResearchResourceStore._targets(self.runtime,cursor,tenant,claims.user_id,task_id,run_id)
                if identity is None or not rows:
                    raise ExecutionRuntimeError('task_unavailable',409)
                self.runtime._key(cursor,claims,tenant,identity[0],rows[0][4])
                for target in targets:
                    self.runtime._connection(cursor,claims,identity[0],target)
                snapshot=self.runtime._strategy(cursor,claims,tenant,identity[1],identity[2],identity[3],targets)
                if snapshot!=identity[4]:
                    raise ExecutionRuntimeError('strategy_conflict',409)
                task,run,_=self.runtime._locks(cursor,claims,tenant,task_id)
                if (run is None or run['run_id']!=run_id or task['status'] not in ('PENDING','RUNNING')
                        or run['status'] not in ('PENDING','RUNNING')):
                    raise ExecutionRuntimeError('task_unavailable',409)
                cursor.execute('SELECT reservation_id,profile_version_id,strategy_version_id,configuration_sha256,minute_limit '
                    'FROM pilot_research_reservations WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s AND run_id=%s FOR UPDATE',
                    (tenant,claims.user_id,task_id,run_id))
                reservation=cursor.fetchone()
                if reservation is None or tuple(reservation[1:4])!=tuple(identity[1:4]):
                    raise ExecutionRuntimeError('resource_unavailable',503)
                cursor.execute("SELECT clock_timestamp() < LEAST(%s,%s + %s * interval '1 minute')",
                    (task['deadline_at'],task['created_at'],reservation[4]))
                if cursor.fetchone()[0] is not True:
                    raise ExecutionRuntimeError('task_unavailable',409)
                cursor.execute('SELECT profile_id,payload,content_sha256 FROM business_profile_versions '
                    'WHERE tenant_id=%s AND profile_version_id=%s',(tenant,identity[1]))
                profile_id,payload,profile_sha=cursor.fetchone()
                cursor.execute('SELECT context,binding FROM pilot_customer_research_contexts '
                    'WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s AND run_id=%s',
                    (tenant,claims.user_id,task_id,run_id))
                previous=cursor.fetchone()
                if previous is None:
                    scope,history=load_research_history(cursor,tenant=tenant,owner=claims.user_id,profile_id=profile_id)
                    context=project_research_context_v2(seller_description=payload.get('description'),
                        profile_sha256=profile_sha,strategy_snapshot=snapshot,
                        reference_time=task['created_at'].isoformat(),history_scope=scope,history=history)
                    compiled=compile_research_context(context)
                    cursor.execute('INSERT INTO pilot_customer_research_contexts '
                        '(tenant_id,owner_user_id,task_id,run_id,reservation_id,profile_version_id,strategy_version_id,'
                        'profile_sha256,configuration_sha256,context,binding) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)',
                        (tenant,claims.user_id,task_id,run_id,reservation[0],identity[1],identity[2],profile_sha,
                         identity[3],compiled['context_json'],json.dumps(compiled['binding'])))
                else:
                    context,binding=previous
                    compiled=compile_research_context(context)
                    if (compiled['binding']!=binding or context['strategy_snapshot']!=snapshot
                            or context['seller_description']!=payload.get('description')
                            or context['profile_sha256']!=profile_sha
                            or context['reference_time']!=task['created_at'].isoformat()):
                        raise ExecutionRuntimeError('strategy_conflict',409)
                self.runtime._active(cursor,claims)
                return compiled
        except ExecutionRuntimeError:
            raise
        except (ResearchContextError,ValueError,TypeError,KeyError,psycopg.Error):
            raise ExecutionRuntimeError('resource_unavailable',503) from None
