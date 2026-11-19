"""Scenario v1 preflight. Trusted context is supplied by the owning harness.

No UI calls, operation reservations, permissions inferred from a template or
capabilities inferred from a valid public request shape.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from .test_client_contract import valid_request

SCHEMA = json.loads(Path(__file__).with_name('scenario-v1.schema.json').read_text(encoding='utf-8'))
_VALIDATOR = Draft202012Validator(SCHEMA)
_FORBIDDEN = {'request_id','operation_id','session_id','snapshot_id','cursor','HWND','PID'}


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,
        separators=(',', ':'),allow_nan=False).encode('utf-8')).hexdigest()


def command_scope(step):
    arguments=deepcopy(step['arguments'])
    if 'finish_focus' in step:
        arguments['params']['finish_focus']=deepcopy(step['finish_focus'])
    return digest({'tool':step['tool'],'arguments':arguments})


def capability_key(step):
    tool, args = step['tool'],step['arguments']
    action = args.get('action', args.get('params',{}).get('condition',{}).get('property','open'))
    variant = 'finish_focus' if tool == 'test_input' and ('finish_focus' in step or 'finish_focus' in args.get('params',{})) else 'scalar'
    if tool == 'test_action' and action == 'click':
        variant=args.get('element',{}).get('selector',{}).get('type','unknown')
    if tool == 'test_input' and action == 'select':
        variant='list' if 'list_value' in args['params']['choice'] else 'selection_table'
    if tool == 'test_table' or tool == 'test_expect' and action == 'row':
        variant='table'
    if tool == 'test_expect' and action == 'editing':
        target_type=args.get('element',{}).get('selector',{}).get('type')
        if target_type in ('table','field'):variant=target_type+'_state'
    if tool == 'test_expect' and action in ('exists','closed') and 'element' not in args:
        variant='window'
    return ':'.join((tool,action,variant,'none'))


def is_mutation(step):
    tool,args=step['tool'],step['arguments']
    return tool not in ('test_inspect','test_expect') and not (
        tool=='test_table' and args.get('action') in ('read','find')
        and args['params'].get('allow_navigation',False) is False)


def _json_value(value, depth=0):
    if depth>32:
        raise ValueError('input_budget_exceeded')
    if isinstance(value,dict):
        if not all(isinstance(k,str) for k in value): raise ValueError('invalid_shape')
        for child in value.values(): _json_value(child,depth+1)
    elif isinstance(value,list):
        for child in value: _json_value(child,depth+1)
    elif type(value) is str:
        if len(value)>65536: raise ValueError('input_budget_exceeded')
    elif type(value) is int:
        if abs(value)>2**53-1: raise ValueError('input_budget_exceeded')
    elif type(value) is not bool and value is not None:
        raise ValueError('invalid_shape')


def _decode(value):
    if not isinstance(value,(str,bytes)): return deepcopy(value)
    if len(value.encode('utf-8') if isinstance(value,str) else value)>1024*1024:
        raise ValueError('input_budget_exceeded')
    def pairs(items):
        result={}
        for k,v in items:
            if k in result: raise ValueError('invalid_json')
            result[k]=v
        return result
    return json.loads(value,object_pairs_hook=pairs)


def _timestamp(value):
    stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
    if stamp.utcoffset()!=timezone.utc.utcoffset(stamp): raise ValueError('context_unavailable')
    return stamp


def _prepare(template, parameters, context, now=None):
    report=dict(version=1,status='rejected',scenario_id=None,revision=None,
        template_digest=None,parameters_digest=None,context_digest=None,plan_digest=None,
        checked_steps=0,total_steps=0,issues=[],issues_truncated=False,runtime_checks=[],
        expires_at=None,dispatch_count=0)
    plans=[]
    rejected,blocked=False,False
    def issue(code,phase,step=None,path='/',block=False):
        nonlocal rejected,blocked
        if block: blocked=True
        else: rejected=True
        if len(report['issues'])<100:
            report['issues'].append(dict(code=code,phase=phase,step_id=step,path=path,detail_code=code))
        else: report['issues_truncated']=True
    try:
        template=_decode(template); parameters=_decode(parameters)
        _json_value(template); _json_value(parameters)
        if len(json.dumps(template,ensure_ascii=False).encode('utf-8'))>256*1024:
            raise ValueError('input_budget_exceeded')
        if not isinstance(template,dict) or not isinstance(parameters,dict): raise ValueError('invalid_shape')
        if type(template.get('version')) is not int or template['version']!=1:
            issue('unsupported_version',1);return report,[]
        errors=list(_VALIDATOR.iter_errors(template))
        for error in errors:
            code='unknown_step' if list(error.path)[-1:]==['tool'] else 'invalid_shape'
            issue(code,1,path='/'+'/'.join(str(x) for x in error.path))
        if errors:return report,[]
        report.update(scenario_id=template['scenario_id'],revision=template['revision'],
            template_digest=digest(template),total_steps=len(template['steps']))
        if template['state']!='reviewed': issue('draft_requires_review',2,block=True)
        if 'recording_review' in template: issue('recording_requires_review',2,block=True)
        for composition in template.get('recording_review',{}).get('compositions',[]):
            if composition['rule'] != 'activate_input_finish_candidate': continue
            step = next((s for s in template['steps'] if s['step_id']==composition['step_id']),None)
            expected = dict(selector=composition['events'][-1]['element']['selector'],same_form=True)
            if step is None or step.get('finish_focus') != expected:
                issue('finish_focus_review_mismatch',2,composition['step_id'],block=True)
        names=set()
        if sum(s['timeout_ms'] for s in template['steps'])>1800000:issue('input_budget_exceeded',2)
        values={}
        for name in parameters.keys()-template['parameters'].keys():issue('unknown_parameter',3,path='/parameters/'+name)
        for name,decl in template['parameters'].items():
            if name not in parameters and decl['required']:
                issue('missing_parameter',3,path='/parameters/'+name);continue
            value=parameters.get(name,decl.get('default'))
            if type(value) is not {'string':str,'boolean':bool,'integer':int}[decl['type']]:
                issue('parameter_type_mismatch',3,path='/parameters/'+name);continue
            values[name]=value
        def resolve(value):
            if isinstance(value,dict):
                if '$param' in value:
                    if set(value)!={'$param'} or value['$param'] not in values:raise ValueError('invalid_parameter_reference')
                    return values[value['$param']]
                if set(value)&_FORBIDDEN or 'id' in value or 'active' in value:raise ValueError('forbidden_runtime_binding')
                return {k:resolve(v) for k,v in value.items()}
            if isinstance(value,list):return [resolve(v) for v in value]
            return value
        for i,step in enumerate(template['steps']):
            sid=step['step_id'];report['checked_steps']+=1
            if sid in names:issue('duplicate_step_id',2,sid)
            names.add(sid)
            try:
                item=deepcopy(step);item['arguments']=resolve(step['arguments'])
                if 'finish_focus' in item:
                    if item['tool'] != 'test_input' or item['arguments'].get('action') != 'text':
                        issue('invalid_finish_focus',2,sid)
                    else:
                        supplied = item['arguments']['params'].get('finish_focus')
                        if supplied is not None and supplied != item['finish_focus']:
                            issue('invalid_finish_focus',2,sid)
                        item['arguments']['params']['finish_focus'] = deepcopy(item['finish_focus'])
                        report['runtime_checks'].append(dict(step_id=sid,
                            checks=['same_live_form','unique_finish_target',
                                    'selected_finish_reference_before_input',
                                    'current_reference_after_finish'],
                            finish_focus=deepcopy(item['finish_focus'])))

                if not valid_request(item['tool'],dict(item['arguments'],request_id='preflight',session_id='preflight',timeout_ms=item['timeout_ms'])):
                    issue('invalid_arguments',3,sid);continue
                if item['on_error']=='continue_observation' and is_mutation(item):issue('unsupported_error_policy',2,sid)
                plans.append(item)
            except ValueError as e:issue(str(e),3,sid)
        report['parameters_digest']=digest(values)
        if len(json.dumps(plans,ensure_ascii=False).encode('utf-8'))>1024*1024:issue('input_budget_exceeded',3)
        required=('owner','channel_id','base_id','approved_base_id','profile_id','session_id','generation',
                  'implementation_revision','platform','mode','policy_id','capability_revision',
                  'observed_at','expires_at','scope_digests','capabilities','manager_mode','session_ready',
                  'allow_mutation','approval_available')
        if not isinstance(context,dict) or any(k not in context for k in required):
            issue('context_unavailable',4,block=True)
        else:
            _json_value(context)
            report['context_digest']=digest(context);report['expires_at']=context['expires_at']
            current=now or datetime.now(timezone.utc)
            observed,expires=_timestamp(context['observed_at']),_timestamp(context['expires_at'])
            if observed>current or expires<=current or observed>=expires:issue('context_expired',4,block=True)
            for k in required[:13]:
                if not isinstance(context[k],str) or not context[k]:issue('context_unavailable',4,block=True)
            if context['base_id']!=context['approved_base_id']:issue('base_mismatch',4,block=True)
            if context['manager_mode'] is not True or context['session_ready'] is not True:issue('session_not_ready',4,block=True)
            if context['policy_id']!=template['data_scope']['policy_id']:issue('data_scope_denied',4,block=True)
            if context['approval_available'] is not True:issue('approval_unavailable',4,block=True)
            if not isinstance(context['scope_digests'],list) or not isinstance(context['capabilities'],dict):raise ValueError('context_unavailable')
            for item in plans:
                sid=item['step_id']
                if command_scope(item) not in context['scope_digests']:issue('data_scope_denied',4,sid,block=True)
                if is_mutation(item) and (template['data_scope']['mutation']!='ui_write' or context['allow_mutation'] is not True):issue('data_scope_denied',4,sid,block=True)
                key=capability_key(item)
                cap=context['capabilities'].get(key,{})
                if not isinstance(cap,dict):cap={}
                supported=cap.get('status')
                if supported!='supported':issue('capability_unsupported' if supported=='unsupported' else 'capability_unknown',5,sid,block=True)
                elif not all(cap.get(k)==context[k] for k in ('platform','mode','implementation_revision')) or not cap.get('evidence'):
                    issue('capability_unknown',5,sid,block=True)
                # Target-dependent/table branches are deliberately not enabled by
                # this first harness runner; their original requirements remain.
                if ':table:' in key or ':selection_table:' in key or ':unknown:' in key or ':group:' in key:
                    issue('capability_unsupported',5,sid,block=True)
                report['runtime_checks'].append(dict(step_id=sid,capability=key,
                    checks=['owner_base_session_generation','scope_and_policy','unique_target','effective_availability','approval']))
        report['status']='rejected' if rejected else 'blocked' if blocked else 'ready'
        indices={step['step_id']:i for i,step in enumerate(template['steps'])}
        report['issues'].sort(key=lambda x:(x['phase'],indices.get(x['step_id'],-1),x['path']))
        if report['status']=='ready':
            report['plan_digest']=digest(dict(template=report['template_digest'],parameters=report['parameters_digest'],context=report['context_digest'],steps=plans))
        return report,plans if report['status']=='ready' else []
    except (ValueError,TypeError,KeyError,RecursionError,AttributeError,OverflowError) as error:
        reason=str(error) if str(error) in ('input_budget_exceeded','invalid_json','invalid_shape','context_unavailable') else 'invalid_shape'
        issue(reason,1,block=reason=='context_unavailable')
        report['status']='rejected' if rejected else 'blocked'
        return report,[]


def preflight_scenario(template, parameters, context):
    """Validate every step; ready is not authorization to skip per-step guards."""
    return _prepare(template,parameters,context)[0]
