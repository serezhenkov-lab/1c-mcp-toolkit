"""Trusted local policy + live public session binding; no harness or execute_code.

Policy files are administrator inputs, never scenario parameters. No implicit
approval, attach, restart, scope expansion or retry of an uncertain mutation.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import time
import uuid

import httpx
from jsonschema import validate
from .scenario_contract import digest, command_scope, capability_key, preflight_scenario
from .scenario_runner import ScenarioRunner

REVISION = 'scenario-context-v1'
REGISTRY = json.loads(Path(__file__).with_name('scenario-capabilities.json').read_text(encoding='utf-8'))
POLICY_SCHEMA = {
    'type':'object','additionalProperties':False,
    'required':['version','channel_id','approved_base_id','profile_id','policy_id','allow_mutation','scope_digests','expires_at'],
    'properties':{'version':{'const':1},'allow_mutation':{'type':'boolean'},
        'scope_digests':{'type':'array','maxItems':100,'uniqueItems':True,'items':{'type':'string','pattern':'^[a-f0-9]{64}$'}},
        **{k:{'type':'string','minLength':1,'maxLength':256} for k in ('channel_id','approved_base_id','profile_id','policy_id','expires_at')}}}

class ContextUnavailable(ValueError):
    pass

def stamp(text):
    value=datetime.fromisoformat(text.replace('Z','+00:00'))
    if value.utcoffset()!=timedelta(0):raise ContextUnavailable('invalid_context_time')
    return value

class ScenarioContextProvider:
    def __init__(self, endpoint, channel, policy_path, *, client=None):
        self.channel=channel
        self.policy_path=Path(policy_path)
        self.client=client or httpx.Client(base_url=endpoint.rstrip('/'),timeout=30,trust_env=False)
        self._owns_client=client is None
        self._issued={}

    def close(self):
        if self._owns_client:self.client.close()

    def transport(self, tool, arguments):
        response=self.client.post('/api/'+tool,params={'channel':self.channel},json=deepcopy(arguments))
        response.raise_for_status()
        return response.json()

    def _observe(self, tool, arguments):
        args=dict(arguments,request_id=str(uuid.uuid4()))
        reply=self.transport(tool,args)
        deadline=time.monotonic()+30
        while reply.get('status') in ('queued','running'):
            if time.monotonic()>=deadline:raise ContextUnavailable('context_observation_timeout')
            operation=reply.get('operation_id')
            if not operation:raise ContextUnavailable('context_unavailable')
            time.sleep(.1)
            polled=self.transport('test_session',dict(request_id=str(uuid.uuid4()),action='status',params={'operation_id':operation},timeout_ms=0))
            reply=(polled.get('data') or {}).get('operation',{})
            if reply.get('operation_id')!=operation:raise ContextUnavailable('operation_identity_mismatch')
        if reply.get('status')!='succeeded':raise ContextUnavailable('context_observation_failed')
        return reply

    def binding(self):
        """Read a live binding for operator review; never derives permissions."""
        reply=self._observe('test_session',dict(action='status',params={},timeout_ms=10000))
        data=reply.get('data') or {};binding=data.get('scenario_binding') or {}
        needed=('owner','base_id','profile_id','generation','implementation_revision','base_mode','channel_id','transport','approval_mode')
        if any(not isinstance(binding.get(k),str) or not binding[k] for k in needed):raise ContextUnavailable('context_unavailable')
        if binding['channel_id']!=self.channel:raise ContextUnavailable('channel_mismatch')
        if data.get('state')!='ready' or data.get('manager_mode') is not True or data.get('supported') is not True:raise ContextUnavailable('session_not_ready')
        sid=data.get('session_id')
        if not sid or binding['generation']!=sid or reply.get('session_id')!=sid:raise ContextUnavailable('session_mismatch')
        observed=stamp(data['observed_at']);now=datetime.now(timezone.utc)
        if observed>now+timedelta(seconds=2) or now-observed>timedelta(seconds=30):raise ContextUnavailable('context_expired')
        return dict(binding,session_id=sid,platform=data['platform_version'],observed_at=data['observed_at'])

    def _policy(self):
        policy=json.loads(self.policy_path.read_text(encoding='utf-8-sig'))
        validate(policy,POLICY_SCHEMA)
        if policy['channel_id']!=self.channel:raise ContextUnavailable('channel_mismatch')
        if stamp(policy['expires_at'])<=datetime.now(timezone.utc):raise ContextUnavailable('policy_expired')
        return policy

    def create(self):
        policy=self._policy();binding=self.binding()
        if binding['base_id']!=policy['approved_base_id']:raise ContextUnavailable('base_mismatch')
        if binding['profile_id']!=policy['profile_id']:raise ContextUnavailable('profile_mismatch')
        mode=binding['base_mode']+'-'+binding['transport']
        capabilities={}
        if binding['implementation_revision']==REGISTRY['implementation_revision'] and binding['platform']==REGISTRY['platform'] and mode in REGISTRY['modes']:
            for key,evidence in REGISTRY['capabilities'].items():
                limitations=[]
                if isinstance(evidence,dict):
                    if mode not in evidence.get('modes',[]):continue
                    limitations=deepcopy(evidence.get('limitations',[]))
                    evidence=evidence['evidence']
                capabilities[key]=dict(status='supported',implementation_revision=binding['implementation_revision'],platform=binding['platform'],mode=mode,evidence=evidence)
                if limitations:capabilities[key]['limitations']=limitations
        expires=min(stamp(binding['observed_at'])+timedelta(seconds=60),stamp(policy['expires_at']))
        context={k:binding[k] for k in ('owner','channel_id','base_id','profile_id','session_id','generation','implementation_revision','platform','observed_at')}
        context.update(approved_base_id=policy['approved_base_id'],mode=mode,policy_id=policy['policy_id'],policy_revision=digest(policy),approval_mode=binding['approval_mode'],capability_revision=digest(REGISTRY),expires_at=expires.isoformat(),scope_digests=deepcopy(policy['scope_digests']),capabilities=capabilities,manager_mode=True,session_ready=True,allow_mutation=policy['allow_mutation'] and binding['approval_mode']!='deny',approval_available=binding['approval_mode'] in ('ask','session_allow'))
        self._issued={k:v for k,v in self._issued.items() if stamp(v['expires_at'])>datetime.now(timezone.utc)}
        if len(self._issued)>=100:raise ContextUnavailable('context_budget_exceeded')
        self._issued[digest(context)]=deepcopy(context)
        return context

    def refresh(self, previous):
        """Renew a context issued here, not a caller-supplied or edited grant."""
        if self._issued.get(digest(previous))!=previous:
            raise ContextUnavailable('context_not_issued')
        return self.create()

    def guard(self, step, context):
        try:
            key=digest(context)
            if self._issued.get(key)!=context or stamp(context['expires_at'])<=datetime.now(timezone.utc):return {'allowed':False}
            policy=self._policy();binding=self.binding()
            if digest(policy)!=context['policy_revision']:return {'allowed':False}
            for name in ('owner','channel_id','base_id','profile_id','session_id','generation','implementation_revision','platform','approval_mode'):
                if binding[name]!=context[name]:return {'allowed':False}
            if binding['base_mode']+'-'+binding['transport']!=context['mode']:return {'allowed':False}
            if command_scope(step) not in policy['scope_digests'] or capability_key(step) not in context['capabilities']:return {'allowed':False}
            # The public executor resolves availability/uniqueness again in the
            # same invocation as the action; this read catches stale targets early.
            args=step['arguments']
            if 'window' in args:
                condition=args.get('params',{}).get('condition',{})
                if step['tool']=='test_expect' and condition.get('property') in ('exists','closed') and 'element' not in args:
                    selector=args['window'].get('selector')
                    if not selector:return {'allowed':False}
                    data=self._observe('test_inspect',dict(action='windows',session_id=context['session_id'],params={},timeout_ms=10000))['data']
                    if data.get('complete') is not True or not isinstance(data.get('windows'),list):return {'allowed':False}
                    matches=[w for w in data['windows'] if all(w.get(k)==v for k,v in selector.items())]
                    return {'allowed':len(matches)<=1,'context_digest':key}
                tree=self._observe('test_inspect',dict(action='tree',session_id=context['session_id'],window=args['window'],params={'depth':32,'max_nodes':5000},timeout_ms=10000))['data']
                if tree.get('complete') is not True:return {'allowed':False}
                if 'element' in args:
                    selector=args['element'].get('selector')
                    if not selector:return {'allowed':False}
                    def walk(nodes,parent=None):
                        for n in nodes:
                            yield n,parent
                            yield from walk(n.get('children',[]),n)
                    matches=[(n,p) for n,p in walk(tree['tree']) if all(n.get(k)==v for k,v in selector.items())]
                    observation=step['tool']=='test_expect' and condition.get('property') in ('exists','visible','enabled','read_only','editing')
                    if observation and condition.get('property')=='exists':
                        if selector.get('type')!='field':return {'allowed':False}
                        # Absence is observable only in a complete, live form tree.
                        return {'allowed':len(matches)<=1,'context_digest':key}
                    if len(matches)!=1:return {'allowed':False}
                    node,parent=matches[0]
                    if observation:
                        # A disabled/hidden field is a valid observation target.
                        # Unknown property values remain unavailable, never false.
                        if type(node.get(condition['property'])) is not bool:return {'allowed':False}
                        return {'allowed':True,'context_digest':key}
                    if node.get('enabled') is not True:return {'allowed':False}
                    if step['tool']=='test_input' and node.get('read_only') is True:return {'allowed':False}
                    page=step['tool']=='test_action' and args.get('action')=='select_page'
                    visibility=step['tool']=='test_expect' and condition.get('property')=='visible'
                    if page and (node.get('type')!='group' or not parent or parent.get('type')!='group'
                                 or parent.get('visible') is not True or parent.get('enabled') is not True):return {'allowed':False}
                    if node.get('visible') is not True and not (node.get('visible') is False and (page or visibility)):return {'allowed':False}
            return {'allowed':True,'context_digest':key}
        except Exception:
            return {'allowed':False}

    def preflight(self, template, parameters):
        context=self.create()
        return preflight_scenario(template,parameters,context),context

    def run(self, template, parameters, *, store_path=None):
        context=self.create()
        return ScenarioRunner(self.transport,self.guard,store_path=store_path,refresh_context=self.refresh).run(template,parameters,context)

    def recover(self, run_id, store_path, *, resume=False):
        context=self.create()
        return ScenarioRunner(self.transport,self.guard,store_path=store_path,refresh_context=self.refresh).recover(run_id,context,resume=resume)


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint',required=True);parser.add_argument('--channel',required=True)
    parser.add_argument('--policy',required=True);parser.add_argument('--template');parser.add_argument('--parameters')
    parser.add_argument('--run',action='store_true');parser.add_argument('--binding',action='store_true')
    parser.add_argument('--store');parser.add_argument('--recover');parser.add_argument('--resume',action='store_true')
    parser.add_argument('--list-runs',action='store_true')
    args=parser.parse_args();provider=ScenarioContextProvider(args.endpoint,args.channel,args.policy)
    try:
        if args.resume and not args.recover:raise ContextUnavailable('resume_requires_recovery')
        if args.list_runs:
            if not args.store or args.run or args.recover or args.binding:raise ContextUnavailable('invalid_recovery_arguments')
            from .scenario_store import RunStore
            result={'runs':RunStore(args.store).list_runs()}
        elif args.recover:
            if not args.store or args.run or args.binding:raise ContextUnavailable('invalid_recovery_arguments')
            result=provider.recover(args.recover,args.store,resume=args.resume)
        elif args.binding:result=provider.binding()
        else:
            template=json.loads(Path(args.template).read_text(encoding='utf-8-sig'))
            parameters=json.loads(Path(args.parameters).read_text(encoding='utf-8-sig'))
            result=provider.run(template,parameters,store_path=args.store) if args.run else provider.preflight(template,parameters)[0]
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except Exception as error:
        print(json.dumps({'status':'blocked','reason':str(error) if isinstance(error,ContextUnavailable) else 'context_unavailable','dispatch_count':0}))
        raise SystemExit(1)
    finally:provider.close()

if __name__=='__main__':main()
