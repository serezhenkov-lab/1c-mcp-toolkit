"""One bounded native identity/focus check using saved input. Never records uilog."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]
source=(root/'tests/test_client/record_native_uilog.py').read_text(encoding='utf-8')
exec(compile(source[:source.index('before = rows()')], 'uilog_helpers', 'exec'))
evidence=root/'openspec/changes/upravlenie-test-klientom/evidence/uilog-native'
recording=json.loads((evidence/'import-fixed.json').read_text(encoding='utf-8'))
value=recording['parameter_values']['value_001']
before=rows();save('baseline',before)
w={'selector':{'form_name':'Документ.T43_Required.ФормаОбъекта'}}
listing={'selector':{'form_name':'Документ.T43_Required.ФормаСписка'}}
created=click(listing,'ФормаСоздать');assert created['status']=='succeeded',created
initial=client_code('Результат=ФормаМенеджераТестирования.ПробаФормыUILog("before");')
save('reference-before',initial)
entered=call('test_input',action='text',window=w,element={'selector':{'name':'ОбязательноеПоле','title':'Обязательное поле','type':'field'}},params={'text':value})
save('input-result',entered)
observed=client_code('Результат=ФормаМенеджераТестирования.ПробаФормыUILog("after");')
save('reference-after',observed)
save('after-input-tree',call('test_inspect',action='tree',window=w))
# Negative control: close/discard this unsaved form and create another of same name.
closed=call('test_action',action='close',window=w);save('close-result',closed)
windows=call('test_inspect',action='windows')
dialogs=[x for x in windows['data']['windows'] if x['form_name']=='MessageBox']
def nodes(items):
    for n in items:
        yield n
        yield from nodes(n.get('children',[]))
if dialogs:
    assert len(dialogs)==1,dialogs
    modal={'id':dialogs[0]['window_id']}
    tree=call('test_inspect',action='tree',window=modal);save('discard-dialog',tree)
    buttons=[n for n in nodes(tree['data']['tree']) if n.get('type')=='button' and n.get('title') in ('Нет','Не сохранять')]
    assert len(buttons)==1,buttons
    answer=call('test_action',action='click',window=modal,element={'id':buttons[0]['element_id']})
    assert answer['status']=='succeeded',answer
windows=call('test_inspect',action='windows')
assert not any(x['form_name']=='Документ.T43_Required.ФормаОбъекта' for x in windows['data']['windows']),windows
recreated=click(listing,'ФормаСоздать');assert recreated['status']=='succeeded',recreated
stale=client_code('Результат=ФормаМенеджераТестирования.ПробаФормыUILog("stale");')
save('old-reference-after-recreate',stale)
new_tree=call('test_inspect',action='tree',window=w);save('recreated-tree',new_tree)
final=rows();save('after-data',final)
checks=dict(input_succeeded=entered['status']=='succeeded',
    native_steps=entered.get('data',{}).get('completed_steps')==['activate','input_text','finish_edit'],
    fresh_title_transition=observed['fresh_form_title']==initial['fresh_form_title']+' *',
    retained_field_identity=observed['same_field_reference'],
    retained_field_observes_value=observed['held_value']==value,
    exact_finish_selected_before=initial['chosen_finish_name']=='Номер',
    actual_focus_is_number=observed['current_name']=='Номер',
    native_focus_equals_preselected=observed['current_equals_chosen'],
    reacquired_form_focus_equals_preselected=observed['fresh_current_equals_chosen'],
    old_reference_not_retargeted=not stale['old_field_readable'] and not stale['old_form_readable'],
    no_document_written=before==final)
save('identity-focus-proof',dict(checks=checks,initial=initial,after=observed,negative_control=stale,
    source_sha256=recording['source_sha256'],new_recording=False,scope='this live form instance and input; no portable UUID assertion'))
print(json.dumps(checks,ensure_ascii=True))
assert all(checks.values()),checks
