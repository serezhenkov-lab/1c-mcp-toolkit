"""Sequential harness runner over public test_* and their shared lifecycle.

Optional durable run links support recovery by observing the existing lifecycle.
No automatic resubmission after an uncertain outcome.
"""
from contextlib import nullcontext
from .scenario_store import RunStore
from copy import deepcopy
from datetime import datetime, timezone
import threading
import time
import uuid

from .scenario_contract import _prepare, digest, is_mutation


class ScenarioRunner:
    def __init__(self, transport, guard, *, poll_interval=0.1, metrics=None, store_path=None, refresh_context=None):
        """transport(tool,args) returns a public envelope; guard(step,context)
        must freshly verify binding/target/capability/approval and return
        {allowed: bool, context_digest: str, reason: str|None}.
        All callbacks, including refresh_context(previous), are trusted adapters,
        never values from the scenario. Renewal changes timestamps only.
        """
        self._refresh=refresh_context
        self._transport=transport
        self._guard=guard
        self._interval=max(0.01,min(poll_interval,1.0))
        self._runs={}
        self._lock=threading.Lock()
        self._metrics=metrics
        self._store=RunStore(store_path) if store_path else None

    @staticmethod
    def _expired(context):
        return datetime.fromisoformat(context['expires_at'].replace('Z','+00:00'))<=datetime.now(timezone.utc)

    def _context_before_step(self, state, step):
        """Renew only elapsed context, between steps; never redispatch a receipt.

        The provider is trusted. Nevertheless renewal may change timestamps only;
        a new session, grant, registry or plan requires a separate reviewed run.
        Persist the audit and new context before any next command can be sent.
        """
        old=state['context']
        if not self._expired(old):return None
        if self._refresh is None:return 'context_expired'
        try:
            fresh=deepcopy(self._refresh(deepcopy(old)))
            stable=lambda c:{k:v for k,v in c.items() if k not in ('observed_at','expires_at')}
            if stable(old)!=stable(fresh):return 'context_refresh_binding_mismatch'
            if any(datetime.fromisoformat(fresh[k].replace('Z','+00:00'))<=datetime.fromisoformat(old[k].replace('Z','+00:00')) for k in ('observed_at','expires_at')):
                return 'context_refresh_not_fresh'
            report,plan=_prepare(state['template'],state['parameters'],fresh)
            if report['status']!='ready' or plan!=state['plan'] or self._expired(fresh):
                return 'context_refresh_preflight_failed'
        except Exception:
            return 'context_refresh_failed'
        event=dict(before_step=step['step_id'],from_digest=digest(old),to_digest=digest(fresh),
                   old_expires_at=old['expires_at'],observed_at=fresh['observed_at'],
                   expires_at=fresh['expires_at'],plan_digest=report['plan_digest'])
        state['context']=fresh
        state['output'].setdefault('context_refreshes',[]).append(event)
        # Storage failures propagate, rather than allowing an unrecorded dispatch.
        self._save(state)
        return None

    def _guarded(self, step, context):
        try:
            if self._expired(context):return False
            value=self._guard(deepcopy(step),deepcopy(context))
            return value.get('allowed') is True and value.get('context_digest')==digest(context) and not self._expired(context)
        except Exception:
            return False

    def _poll(self, operation_id, session_id):
        reply=self._transport('test_session',dict(action='status',session_id=session_id,
            request_id=str(uuid.uuid4()),params={'operation_id':operation_id},timeout_ms=0))
        return (reply.get('data') or {}).get('operation',{})

    def _terminal(self, reply, arguments, timeout_ms):
        started=time.monotonic()
        operation_id=reply.get('operation_id')
        while reply.get('status') in ('queued','running'):
            if not operation_id or time.monotonic()-started>=timeout_ms/1000:
                return dict(status='unknown',operation_id=operation_id,error={'code':'runner_wait_expired'})
            time.sleep(self._interval)
            reply=self._poll(operation_id,arguments['session_id'])
            if reply.get('operation_id')!=operation_id:
                return dict(status='unknown',operation_id=operation_id,error={'code':'operation_unavailable'})
        if operation_id and reply.get('operation_id')!=operation_id:
            return dict(status='unknown',operation_id=operation_id,error={'code':'operation_identity_mismatch'})
        return reply

    def _save(self, state):
        if self._store is not None:self._store.save(state)

    def run(self, template, parameters, context):
        with self._store.locked() if self._store else nullcontext():
            return self._run(template, parameters, context)

    def _run(self, template, parameters, context):
        """Create a new run. Validation covers the entire plan before dispatch."""
        if not self._lock.acquire(blocking=False):
            return dict(status='blocked',reason='runner_busy',run_id=None,steps=[],dispatch_count=0)
        try:
            context=deepcopy(context)
            preflight,plan=_prepare(template,parameters,context)
            output=dict(status=preflight['status'],run_id=None,preflight=preflight,steps=[],dispatch_count=0)
            if preflight['status']!='ready':return output
            run_id=str(uuid.uuid4())
            output['run_id']=run_id
            state=dict(version=1,output=output,context=context,plan=plan,entries={},template=deepcopy(template),parameters=deepcopy(parameters))
            self._runs[run_id]=state
            self._save(state)
            return self._execute(state)
        finally:
            self._lock.release()

    @staticmethod
    def _observation_failure(step, reply):
        return (reply.get('status')=='failed' and not is_mutation(step)
                and step['on_error']=='continue_observation'
                and (reply.get('error') or {}).get('code') not in (
                    'permission_denied','approval_rejected','approval_expired',
                    'connection_lost','session_not_ready','result_expired','operation_result_unavailable'))

    def _execute(self, state, start=0, observation_only=False):
        output=state['output'];context=state['context'];plan=state['plan']
        run_id=output['run_id']
        for step in plan[start:]:
            execution_id=str(uuid.uuid5(uuid.UUID(run_id),step['step_id']))
            request_id=str(uuid.uuid5(uuid.UUID(execution_id),'public-command'))
            entry=dict(step_id=step['step_id'],step_execution_id=execution_id,
                request_id=request_id,operation_id=None,status='not_started',result=None)
            refresh_error=None if observation_only and is_mutation(step) else self._context_before_step(state,step)
            context=state['context']
            output['steps'].append(entry)
            arguments=dict(deepcopy(step['arguments']),request_id=request_id,
                session_id=context['session_id'],timeout_ms=step['timeout_ms'])
            state['entries'][step['step_id']]=dict(entry=entry,arguments=arguments,step=step)
            if observation_only and is_mutation(step):
                entry.update(status='skipped');self._save(state);continue
            if refresh_error or not self._guarded(step,context):
                entry.update(status='blocked',result={'error':{'code':refresh_error or 'runtime_precondition_failed'}})
                output['status']='partial' if output['dispatch_count'] else 'blocked'
                break
            metric_token=None
            if self._metrics is not None:
                try:metric_token=self._metrics.begin()
                except Exception:pass
            try:
                entry['status']='dispatching'
                output['dispatch_count']+=1
                self._save(state)
                reply=self._transport(step['tool'],deepcopy(arguments))
                entry['operation_id']=reply.get('operation_id')
                self._save(state)
                reply=self._terminal(reply,arguments,step['timeout_ms'])
                if reply.get('request_id') not in (None,request_id):
                    reply=dict(status='unknown',error={'code':'request_identity_mismatch'})
            except Exception:
                reply=dict(status='unknown',error={'code':'transport_outcome_unknown'})
            status=reply.get('status')
            if status=='succeeded' and (not reply.get('operation_id') or reply.get('request_id')!=request_id):
                reply=dict(status='unknown',error={'code':'operation_identity_unproven'})
                status='unknown'
            if status not in ('succeeded','failed','unknown','awaiting_approval','cancelled'):
                status='unknown'
            entry.update(status=status,result=deepcopy(reply))
            if self._metrics is not None:
                try:
                    entry['metrics']=self._metrics.finish(metric_token,run_id=run_id,
                        step_execution_id=execution_id,operation_id=entry['operation_id'],
                        session_id=context['session_id'])
                except Exception:
                    entry['metrics']={'available':False,'reason':'diagnostics_failed'}
            self._save(state)
            if status=='succeeded':continue
            if self._observation_failure(step,reply):
                observation_only=True;continue
            output['status']=status if status in ('unknown','awaiting_approval') else 'partial' if any(s['status']=='succeeded' for s in output['steps']) else 'failed'
            break
        else:
            output['status']='partial' if observation_only else 'succeeded'
        self._save(state)
        return deepcopy(output)

    def recover(self, run_id, context, *, resume=False):
        """Observe retained operations; only explicit resume dispatches new steps."""
        if self._store is None:
            return dict(status='blocked',reason='run_store_required',dispatch_count=0)
        with self._lock, self._store.locked():
            state=self._store.load(run_id)
            old=state['context'];context=deepcopy(context)
            binding=('owner','channel_id','base_id','approved_base_id','profile_id',
                     'session_id','generation','implementation_revision','platform','mode',
                     'policy_id','policy_revision','capability_revision','approval_mode')
            if any(old.get(k)!=context.get(k) for k in binding):
                return dict(status='blocked',reason='recovery_binding_mismatch',run_id=run_id,dispatch_count=0)
            report,plan=_prepare(state['template'],state['parameters'],context)
            if report['status']!='ready' or plan!=state['plan']:
                return dict(status='blocked',reason='recovery_preflight_failed',run_id=run_id,dispatch_count=0)
            output=state['output']
            observation_only=False
            for index,entry in enumerate(output['steps']):
                step=plan[index]
                if entry['status']=='skipped' and observation_only and is_mutation(step) and not entry['operation_id']:
                    continue
                op=entry['operation_id']
                if not op:
                    if entry['status']=='dispatching':entry['status']='unknown'
                    output.update(status='unknown',reason='operation_identity_unavailable')
                    self._save(state);return deepcopy(output)
                try:
                    reply=self._poll(op,context['session_id'])
                    if (reply.get('operation_id')!=op or reply.get('request_id')!=entry['request_id']
                            or reply.get('session_id') not in (None,context['session_id'])):
                        raise ValueError('identity')
                except Exception:
                    output.update(status='unknown',reason='operation_result_unavailable')
                    self._save(state);return deepcopy(output)
                entry['reconciliation']=deepcopy(reply)
                if reply.get('status')!='succeeded':
                    if entry['status']!='unknown' and self._observation_failure(step,reply):
                        entry.update(status='failed',result=deepcopy(reply))
                        observation_only=True
                        continue
                    if reply.get('status') in ('failed','cancelled') and entry['status']!='unknown':
                        entry.update(status=reply['status'],result=deepcopy(reply))
                        output.update(status='partial' if index else 'failed',reason='step_policy_stopped')
                        self._save(state);return deepcopy(output)
                    output.update(status='unknown' if reply.get('status') not in ('queued','running','awaiting_approval') else reply['status'],reason='reconciliation_required')
                    self._save(state);return deepcopy(output)
                # Preserve the original unknown and the separately observed result.
                if entry['status']!='unknown':entry.update(status='succeeded',result=deepcopy(reply))
            state['context']=context
            output.pop('reason',None)
            output['recovery_preflight']=report
            output['status']='recovered' if len(output['steps'])<len(plan) else 'partial' if observation_only else 'succeeded'
            output['observation_only']=observation_only
            self._save(state)
            if resume and len(output['steps'])<len(plan):
                self._execute(state,start=len(output['steps']),observation_only=observation_only)
            if any(e['status']=='unknown' for e in output['steps']):
                output['status']='partial';output['reason']='reconciled_unknown_preserved'
            self._save(state)
            return deepcopy(output)

    def retry_delivery(self, run_id, step_id, *, plan_digest):
        """Explicit identical delivery only for a retained successful operation.
        No resume/retry for unknown, awaiting approval, expired or lost handles.
        """
        with self._lock:
            state=self._runs.get(run_id)
            if state is None:return dict(status='blocked',reason='run_state_unavailable')
            if state['output']['status'] in ('unknown','awaiting_approval'):
                return dict(status='blocked',reason='reconciliation_required')
            if plan_digest!=state['output']['preflight']['plan_digest']:
                return dict(status='rejected',reason='run_payload_mismatch')
            saved=state['entries'].get(step_id)
            if not saved or saved['entry']['status']!='succeeded' or not saved['entry']['operation_id']:
                return dict(status='blocked',reason='reconciliation_required')
            if not self._guarded(saved['step'],state['context']):
                return dict(status='blocked',reason='runtime_precondition_failed')
            op=saved['entry']['operation_id']
            try:
                current=self._poll(op,state['context']['session_id'])
                if current.get('operation_id')!=op or current.get('status')!='succeeded':
                    return dict(status='blocked',reason='operation_result_unavailable')
                reply=self._transport(saved['step']['tool'],deepcopy(saved['arguments']))
                if reply.get('operation_id')!=op or reply.get('status')!='succeeded':
                    return dict(status='unknown',reason='replay_not_confirmed')
                return deepcopy(reply)
            except Exception:
                return dict(status='unknown',reason='transport_outcome_unknown')
