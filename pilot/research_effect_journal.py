"""Authenticated effect journal; no network, automatic restart, or refunds."""
from datetime import datetime
import json
from uuid import UUID, uuid5

import psycopg

from pilot.customer_research_context import CustomerResearchContextStore
from pilot.execution_contract import ExecutionRuntimeError, canonical_uuid
from pilot.research_context import ResearchContextError, compile_research_context
from pilot.research_effect_contract import effect_input, effect_result, canonical_effect_sha256, known_read_failure
from pilot.research_resources import _event
from pilot.research_quote import ResearchQuoteRule


_FIELDS = ('task_id','run_id','sequence','generation','coordinator_owner','kind','payload',
           'input_sha256','context_binding','action_id','permit_id','deadline_at',
           'status','result','output_sha256')


def _scope(task_id, run_id, sequence):
    task_id,run_id=map(canonical_uuid,(task_id,run_id))
    if type(sequence) is not int or not 1<=sequence<=1000:
        raise ExecutionRuntimeError('invalid_request',422)
    return task_id,run_id,str(uuid5(UUID(run_id),f'{task_id}:{sequence}'))


def _entry(row):
    value=dict(zip(_FIELDS,row))
    value['deadline_at']=value['deadline_at'].isoformat()
    return value


class ResearchEffectJournal:
    def __init__(self, resources):
        self.resources=resources
        self.runtime=resources.runtime

    @staticmethod
    def _select(cursor,tenant,user,task_id,run_id,sequence,*,lock=False):
        cursor.execute('SELECT '+','.join(_FIELDS)+' FROM pilot_research_effect_journal '
            'WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s AND run_id=%s AND sequence=%s'
            +(' FOR UPDATE' if lock else ''),(tenant,user,task_id,run_id,sequence))
        row=cursor.fetchone()
        return None if row is None else _entry(row)

    @staticmethod
    def _context(cursor,tenant,user,task_id,run_id,binding,snapshot):
        cursor.execute('SELECT context,binding FROM pilot_customer_research_contexts '
            'WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s AND run_id=%s',
            (tenant,user,task_id,run_id))
        row=cursor.fetchone()
        if row is None:
            raise ExecutionRuntimeError('request_conflict',409)
        context,stored_binding=row
        if (compile_research_context(context)['binding']!=binding or stored_binding!=binding
                or context['strategy_snapshot']!=snapshot):
            raise ExecutionRuntimeError('request_conflict',409)

    @staticmethod
    def _coordinator(cursor,tenant,user,task_id,run_id,generation,owner):
        cursor.execute('SELECT run_id,generation,current_owner,lease_expires_at,phase,clock_timestamp() '
            'FROM pilot_research_runtime WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s FOR UPDATE',
            (tenant,user,task_id))
        row=cursor.fetchone()
        if (row is None or tuple(row[:3])!=(run_id,generation,owner) or row[4]!='RUNNING'
                or row[3] is None or row[3]<=row[5]):
            raise ExecutionRuntimeError('request_conflict',409)
        return row[3]

    def _current(self,cursor,claims,tenant,task_id,run_id,binding):
        """Revalidate replay in its own transaction, including current material revocations."""
        cursor.execute('SELECT device_id,profile_version_id,strategy_version_id,configuration_sha256,'
            'configuration_snapshot FROM pilot_collection_tasks WHERE tenant_id=%s AND owner_user_id=%s '
            'AND task_id=%s',(tenant,claims.user_id,task_id))
        identity=cursor.fetchone()
        rows,targets=self.resources._targets(self.runtime,cursor,tenant,claims.user_id,task_id,run_id)
        if identity is None or not rows:
            raise ExecutionRuntimeError('task_unavailable',409)
        self.runtime._key(cursor,claims,tenant,identity[0],rows[0][4])
        for target in targets:
            self.runtime._connection(cursor,claims,identity[0],target)
        snapshot=self.runtime._strategy(cursor,claims,tenant,identity[1],identity[2],identity[3],targets)
        if snapshot!=identity[4]:
            raise ExecutionRuntimeError('request_conflict',409)
        try:
            capable=self.resources.research_capability(json.loads(json.dumps(snapshot)))
        except Exception:
            capable=False
        if capable is not True:
            raise ExecutionRuntimeError('capability_unavailable',501)
        task,run,_=self.runtime._locks(cursor,claims,tenant,task_id)
        if (run is None or run['run_id']!=run_id or task['status'] not in ('PENDING','RUNNING')
                or run['status'] not in ('PENDING','RUNNING')):
            raise ExecutionRuntimeError('task_unavailable',409)
        cursor.execute("SELECT clock_timestamp()<LEAST(%s,%s+minute_limit*interval '1 minute'),rule_version,rule_sha256 "
            'FROM pilot_research_reservations WHERE tenant_id=%s AND owner_user_id=%s '
            'AND task_id=%s AND run_id=%s FOR UPDATE',
            (task['deadline_at'],task['created_at'],tenant,claims.user_id,task_id,run_id))
        reservation=cursor.fetchone()
        if reservation is None or reservation[0] is not True:
            raise ExecutionRuntimeError('task_unavailable',409)
        rule=self.resources.rule
        if not isinstance(rule,ResearchQuoteRule) or reservation[1:]!=(rule.ruleVersion,rule.digest()):
            raise ExecutionRuntimeError('resource_unavailable',503)
        self._context(cursor,tenant,claims.user_id,task_id,run_id,binding,snapshot)

    def begin(self,claims,*,task_id,run_id,sequence,generation,coordinator_owner,
              context_binding,kind,payload):
        task_id,run_id,action_id=_scope(task_id,run_id,sequence)
        owner=canonical_uuid(coordinator_owner)
        if type(generation) is not int or not 1<=generation<=2147483647:
            raise ExecutionRuntimeError('invalid_request',422)
        payload,digest=effect_input(kind,payload,context_binding)
        binding=json.loads(json.dumps(context_binding))
        # This loader finishes before resource.begin obtains profile/task locks.
        compiled=CustomerResearchContextStore(self.runtime).load(claims,task_id=task_id,run_id=run_id)
        if compiled['binding']!=binding:
            raise ExecutionRuntimeError('request_conflict',409)
        deadline=None

        def admission(cursor,tenant,event):
            nonlocal deadline
            self._context(cursor,tenant,claims.user_id,task_id,run_id,binding,event['strategy_snapshot'])
            lease=self._coordinator(cursor,tenant,claims.user_id,task_id,run_id,generation,owner)
            cursor.execute('SELECT '+','.join(_FIELDS)+' '
                'FROM pilot_research_effect_journal WHERE tenant_id=%s AND owner_user_id=%s '
                'AND task_id=%s AND run_id=%s ORDER BY sequence',(tenant,claims.user_id,task_id,run_id))
            previous=[_entry(row) for row in cursor.fetchall()]
            if [entry['sequence'] for entry in previous]!=list(range(1,sequence)):
                raise ExecutionRuntimeError('request_conflict',409)
            for entry in previous:
                row=self.resources._select(cursor,tenant,claims.user_id,task_id,run_id,entry['action_id'])
                if (row is None or entry['context_binding']!=binding
                        or not self.prior_effect_valid(entry,_event(row))
                        or kind=='READ' and entry['status']=='FAILED' and entry['payload']==payload):
                    raise ExecutionRuntimeError('request_conflict',409)
            deadline=min(lease,event['deadline'])
            return True

        def issued(cursor,tenant,event):
            cursor.execute('INSERT INTO pilot_research_effect_journal(tenant_id,owner_user_id,task_id,run_id,'
                'sequence,generation,coordinator_owner,kind,payload,input_sha256,context_binding,action_id,permit_id,deadline_at) '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s::jsonb,%s,%s,%s)',
                (tenant,claims.user_id,task_id,run_id,sequence,generation,owner,kind,json.dumps(payload),digest,
                 json.dumps(binding),action_id,event['permit_id'],deadline))

        try:
            grant=self.resources.begin(claims,task_id=task_id,run_id=run_id,action_id=action_id,
                resource='MODEL_CALL' if kind=='MODEL' else 'SOURCE_READ',input_sha256=digest,
                _admission=admission,_on_issued=issued)
            with self.runtime.database.connect() as connection,connection.cursor() as cursor:
                tenant=self.runtime._active(cursor,claims)
                self._current(cursor,claims,tenant,task_id,run_id,binding)
                self._coordinator(cursor,tenant,claims.user_id,task_id,run_id,generation,owner)
                # Same lock order as finish: event before journal. Read current, not stale begin result.
                event_row=self.resources._select(cursor,tenant,claims.user_id,task_id,run_id,action_id,lock=True)
                entry=self._select(cursor,tenant,claims.user_id,task_id,run_id,sequence,lock=True)
                if (entry is None or event_row is None or entry['generation']!=generation
                        or entry['coordinator_owner']!=owner or entry['kind']!=kind or entry['payload']!=payload
                        or entry['context_binding']!=binding or entry['input_sha256']!=digest
                        or entry['action_id']!=action_id or entry['permit_id']!=grant['event']['permit_id']):
                    raise ExecutionRuntimeError('request_conflict',409)
                self._matching_event(entry,_event(event_row))
                if entry['status']=='SUCCEEDED' or entry['status']=='FAILED' and entry['result'] is not None:
                    if not self.prior_effect_valid(entry,_event(event_row)):
                        raise ExecutionRuntimeError('request_conflict',409)
                self.runtime._active(cursor,claims)
                return dict(created=grant['created'],entry=entry)
        except ExecutionRuntimeError:
            raise
        except (psycopg.Error,ResearchContextError,ValueError,TypeError,KeyError):
            raise ExecutionRuntimeError('resource_unavailable',503) from None

    @staticmethod
    def _matching_event(entry,event):
        if (any(entry[key]!=event[key] for key in ('task_id','run_id','action_id','permit_id'))
                or entry['input_sha256']!=event['input_sha256']
                or entry['status']!=event['status'] or entry['output_sha256']!=event['output_sha256']
                or event['resource']!=('MODEL_CALL' if entry['kind']=='MODEL' else 'SOURCE_READ')
                or datetime.fromisoformat(entry['deadline_at'])>datetime.fromisoformat(event['deadline_at'])):
            raise ExecutionRuntimeError('request_conflict',409)

    @classmethod
    def prior_effect_valid(cls,entry,event):
        """Strict paired final receipt check shared by admission and supervisor."""
        try:
            cls._matching_event(entry,event)
            _,_,action_id=_scope(entry['task_id'],entry['run_id'],entry['sequence'])
            payload,digest=effect_input(entry['kind'],entry['payload'],entry['context_binding'])
            if entry['action_id']!=action_id or entry['input_sha256']!=digest:
                return False
            if entry['status']=='SUCCEEDED':
                result=effect_result(entry['kind'],payload,entry['result'])
            elif entry['status']=='FAILED':
                result=known_read_failure(entry['kind'],payload,entry['result'])
            else:
                return False
            return canonical_effect_sha256(result)==entry['output_sha256']
        except (ExecutionRuntimeError,KeyError,TypeError,ValueError):
            return False

    def finish(self,claims,*,task_id,run_id,sequence,permit_id,status,result=None):
        task_id,run_id,action_id=_scope(task_id,run_id,sequence)
        permit_id=canonical_uuid(permit_id)
        if type(status) is not str or status not in ('SUCCEEDED','FAILED','UNKNOWN') \
                or (status=='UNKNOWN' and result is not None):
            raise ExecutionRuntimeError('invalid_request',422)
        try:
            with self.runtime.database.connect() as connection,connection.cursor() as cursor:
                tenant=self.runtime._active(cursor,claims)
                event_row=self.resources._select(cursor,tenant,claims.user_id,task_id,run_id,action_id,lock=True)
                entry=self._select(cursor,tenant,claims.user_id,task_id,run_id,sequence,lock=True)
                if entry is None or event_row is None or entry['permit_id']!=permit_id:
                    raise ExecutionRuntimeError('request_not_found',404)
                self._matching_event(entry,_event(event_row))
                output=effect_result(entry['kind'],entry['payload'],result) if status=='SUCCEEDED' else None
                if status=='FAILED' and result is not None:
                    output=known_read_failure(entry['kind'],entry['payload'],result)
                digest=canonical_effect_sha256(output) if output is not None else None
                if entry['status']!='ISSUED':
                    if entry['status']!=status or entry['output_sha256']!=digest or entry['result']!=output:
                        raise ExecutionRuntimeError('request_conflict',409)
                else:
                    cursor.execute('UPDATE pilot_research_resource_events SET status=%s,output_sha256=%s,'
                        'finished_at=clock_timestamp() WHERE tenant_id=%s AND owner_user_id=%s AND permit_id=%s',
                        (status,digest,tenant,claims.user_id,permit_id))
                    cursor.execute('UPDATE pilot_research_effect_journal SET status=%s,result=%s::jsonb,output_sha256=%s '
                        'WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s AND run_id=%s AND sequence=%s RETURNING '+','.join(_FIELDS),
                        (status,json.dumps(output) if output is not None else None,digest,tenant,claims.user_id,task_id,run_id,sequence))
                    entry=_entry(cursor.fetchone())
                self.runtime._active(cursor,claims)
                return entry
        except ExecutionRuntimeError:
            raise
        except (psycopg.Error,ResearchContextError,ValueError,TypeError,KeyError):
            raise ExecutionRuntimeError('resource_unavailable',503) from None
