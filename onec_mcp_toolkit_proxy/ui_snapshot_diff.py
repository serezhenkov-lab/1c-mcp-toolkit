"""Read-only diff of trusted test_inspect/tree captures, not image/row diff.

Capture bindings must come from the same authorized collector. The opaque
registered window ID anchors registry generation; root IDs anchor the form.
No target lookup, text matching, transport, UI mutation or operation retry.
"""
from copy import deepcopy
import json

PROPERTIES = ('name','title','visible','enabled','read_only','editing')
BINDING = ('owner','channel_id','base_id','session_id','generation','window_id','scope','data_policy_id')


def diff_ui_snapshots(before, after):
    """Inputs: {binding, result}; result is a public test_inspect/tree envelope.
    Both reads must explicitly target binding.window_id in the same registry.
    scope is the requested subtree (window root or registered element ID).
    """
    out=dict(version=1,status='unavailable',equal=None,reason=None,
        scope='form_tree_properties',sources=[],coverage=[],added=[],removed=[],changed=[],
        unavailable_properties=[],unobserved_ids=[],counts=None,diff_truncated=False,
        excluded_scopes=['table_rows','command_interface','command_bars','table_additions','images'])
    def fail(reason):
        out['reason']=reason
        return out
    try:
        if len(json.dumps([before,after],ensure_ascii=False,allow_nan=False).encode('utf-8'))>2*1024*1024:
            return fail('input_budget_exceeded')
        for capture in (before,after):
            if not isinstance(capture,dict) or set(capture)!={'binding','result'}:return fail('invalid_capture')
            binding=capture['binding'];result=capture['result']
            if not isinstance(binding,dict) or any(not isinstance(binding.get(k),str) or not binding[k] for k in BINDING):
                return fail('identity_unproven')
            if binding.get('generation_proof')!='registry_window_id' or binding['generation']!=binding['window_id']:
                return fail('generation_unproven')
            if result.get('status')!='succeeded':return fail('observation_failed')
            if result.get('session_id')!=binding['session_id']:return fail('session_mismatch')
            data=result.get('data',{})
            if not isinstance(data.get('snapshot_id'),str) or not data['snapshot_id'] or not isinstance(data.get('tree'),list):
                return fail('invalid_snapshot')
            out['sources'].append(dict(snapshot_id=data['snapshot_id'],operation_id=result.get('operation_id'),
                observed_at=result.get('observed_at'),expires_at=data.get('expires_at'),binding=deepcopy(binding)))
            out['coverage'].append(deepcopy(data.get('coverage',[])))
        for key in BINDING:
            if before['binding'][key]!=after['binding'][key]:return fail(key+'_mismatch')
        def flatten(data):
            found={};roots=[];todo=[(node,None,0) for node in reversed(data['tree'])]
            while todo:
                node,parent,depth=todo.pop()
                if depth>32 or len(found)>=5000:raise ValueError('input_budget_exceeded')
                if not isinstance(node,dict):raise ValueError('invalid_node')
                identity=node.get('element_id')
                if not isinstance(identity,str) or not identity:raise ValueError('identity_unproven')
                if identity in found:raise ValueError('duplicate_identity')
                if not isinstance(node.get('type'),str) or not isinstance(node.get('children'),list):raise ValueError('invalid_node')
                if not isinstance(node.get('unavailable'),list):raise ValueError('property_availability_unproven')
                found[identity]=(node,parent)
                if parent is None:roots.append(identity)
                todo.extend((child,identity,depth+1) for child in reversed(node['children']))
            return found,roots
        left,lroots=flatten(before['result']['data']);right,rroots=flatten(after['result']['data'])
        if not lroots or lroots!=rroots:return fail('root_identity_mismatch')
        for identity in left.keys() & right.keys():
            if left[identity][0]['type']!=right[identity][0]['type']:return fail('identity_type_mismatch')
        def complete(data,nodes):
            coverage=data.get('coverage')
            if not isinstance(coverage,list):return False
            entries=[c for c in coverage if isinstance(c,dict) and c.get('scope')=='form_tree']
            return (data.get('complete') is True and data.get('truncated') is False
                    and len(entries)==1 and entries[0].get('status')=='complete'
                    and all(n['type']!='unsupported' for n,_ in nodes.values()))
        full=complete(before['result']['data'],left) and complete(after['result']['data'],right)
        for identity,(node,parent) in left.items():
            if identity not in right:
                if full:out['removed'].append(dict(element_id=identity,parent_id=parent,type=node['type']))
                else:out['unobserved_ids'].append(dict(element_id=identity,missing_from='after'))
                continue
            other,other_parent=right[identity];changes=[]
            if parent!=other_parent:
                if full:changes.append(dict(property='parent_id',before=parent,after=other_parent))
                else:out['unavailable_properties'].append(dict(element_id=identity,property='parent_id',reason='partial_hierarchy'))
            for prop in PROPERTIES:
                if prop not in node or prop not in other or prop in node['unavailable'] or prop in other['unavailable']:
                    out['unavailable_properties'].append(dict(element_id=identity,property=prop,reason='property_unavailable'))
                elif type(node[prop]) is not type(other[prop]) or node[prop]!=other[prop]:
                    changes.append(dict(property=prop,before=node[prop],after=other[prop]))
            if changes:out['changed'].append(dict(element_id=identity,changes=changes))
        for identity,(node,parent) in right.items():
            if identity not in left:
                if full:out['added'].append(dict(element_id=identity,parent_id=parent,type=node['type']))
                else:out['unobserved_ids'].append(dict(element_id=identity,missing_from='before'))
        out['counts']={k:len(out[k]) for k in ('added','removed','changed','unavailable_properties','unobserved_ids')}
        differs=bool(out['added'] or out['removed'] or out['changed'])
        out['status']='different' if full and differs else 'equal' if full and not out['unavailable_properties'] else 'partial'
        out['equal']=False if differs else True if out['status']=='equal' else None
        out['reason']=None if out['status'] in ('equal','different') else 'incomplete_observation'
        # Bound presentation, not the globally computed counts/status.
        total=0;count=0;stopped=False
        for key in ('added','removed','changed','unavailable_properties','unobserved_ids'):
            kept=[]
            for entry in out[key]:
                size=len(json.dumps(entry,ensure_ascii=False).encode('utf-8'))
                if stopped or total+size>250*1024 or count>=100:
                    stopped=True;continue
                kept.append(entry);total+=size;count+=1
            out[key]=kept
        out['diff_truncated']=stopped
        return deepcopy(out)
    except (ValueError,TypeError,KeyError,AttributeError,RecursionError):
        # No partial differences on malformed input.
        out.update(status='unavailable',equal=None,reason='invalid_snapshot',counts=None,
            added=[],removed=[],changed=[],unavailable_properties=[],unobserved_ids=[])
        return out
