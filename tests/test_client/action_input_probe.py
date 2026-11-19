"""Single diagnostic input; save original exception and observations, no retry."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]
source=(root/'tests/test_client/record_native_uilog.py').read_text(encoding='utf-8')
exec(compile(source[:source.index('before = rows()')], 'uilog_helpers', 'exec'))
w={'selector':{'title':'Action Fixture'}};el={'selector':{'name':'Текст','type':'field'}}
before=rows();save('baseline',before)
save('windows-before',call('test_inspect',action='windows'))
save('tree-before',call('test_inspect',action='tree',window=w))
if '--activate-first' in sys.argv:
    activated=call('test_action',action='activate_window',window=w)
    save('activate-window',activated)
    assert activated['status']=='succeeded',activated
reply=call('test_input',action='text',window=w,element=el,params={'text':'TASK021_DIAGNOSTIC','finish_focus':{'selector':{'name':'Флаг','type':'field'},'same_form':True}})
save('diagnostic-input',reply)
save('windows-after',call('test_inspect',action='windows'))
save('values-after',call('test_inspect',action='values',window=w,params={'targets':[el]}))
after=rows();save('after-data',after)
check('no_document_write',before==after)
save('diagnostic-summary',dict(status=reply['status'],exception=reply['data'].get('probe_exception'),completed_steps=reply['data'].get('completed_steps'),new_recording=False,retry=False))
