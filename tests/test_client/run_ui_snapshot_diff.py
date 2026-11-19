"""12.1 isolated public inspect captures and pure diff checks."""
from pathlib import Path
from datetime import datetime,timezone
from copy import deepcopy
import hashlib
import json
import shutil
import socket
import sys

root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root));sys.path.insert(0,str(root/'tests'))
from onec_mcp_toolkit_proxy.ui_snapshot_diff import diff_ui_snapshots

run_name='ui-diff-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
folder=root/'.local'/run_name
(folder/'http/db').mkdir(parents=True)
shutil.copy2(root/'.local/profile-runtime/db/1Cv8.1CD',folder/'http/db/1Cv8.1CD')
toolkit_epf=root/'.local/queue2-final/Toolkit-production.epf'
fixture_epf=root/'.local/queue2-final/Fixture.epf'
source=(root/'tests/test_client/run_queue1_finish.py').read_text(encoding='utf-8')
prefix=source[:source.index('try:\n    barrier =')]
prefix=prefix.replace("'.local/queue1-finish'",repr('.local/'+run_name))
prefix=prefix.replace('17669','17699').replace("str(stand / 'Toolkit.epf')","str(toolkit_epf)")
prefix=prefix.replace("ANONYMIZATION_ENABLED='false'","ANONYMIZATION_ENABLED='false', RESPONSE_FORMAT='json'")
exec(compile(prefix,'scenario_stand_helpers','exec'))


def capture_tree(**params):
    response=complete('test_inspect',args(action='tree',session_id=sid,window={'id':wid},params=params))
    assert response.get('status')=='succeeded',response
    return dict(binding=dict(owner='isolated-harness',channel_id='queue1',base_id=base_id,
        session_id=sid,generation=wid,window_id=wid,generation_proof='registry_window_id',
        scope='window',data_policy_id='raw-stand'),result=response)

try:
    proxy=start_proxy()
    command=f'"{exe}" ENTERPRISE /IBConnectionString "File=""{run / "db"}"";" /TESTCLIENT -TPort16569 /N ApiProbe /Execute "{fixture_epf}" /DisableStartupDialogs /DisableStartupMessages /Out "{run / "client.log"}"'
    testclient=launch(command,'client')
    for _ in range(120):
        try:
            with socket.create_connection(('127.0.0.1',16569),timeout=.3):break
        except OSError:time.sleep(.5)
    else:raise AssertionError('client_not_ready')
    manager=start_manager();ready()
    code('ТестПрофильID="ui_diff"; ТестПрофильПользователь="ApiProbe"; ТестПрофильПорт=16569; ТестПрофильВключен=Истина; ТестПрофильТребуетПароль=Ложь; СохранитьПрофильТестирования(Неопределено); Результат=ТестПрофильСтатус;')
    attached=complete('test_session',args(action='attach',params={'profile_id':'ui_diff'}))
    assert attached.get('status')=='succeeded',attached
    sid=attached['session_id']
    connection=code('Результат=СтрокаСоединенияИнформационнойБазы();','server')
    assert str((run/'db').resolve()).casefold().replace('\\','/') in str(connection).casefold().replace('\\','/')
    version=code('Информация=Новый СистемнаяИнформация; Результат=Информация.ВерсияПриложения;','server')
    assert version=='8.5.1.1529'
    base_id=hashlib.sha256(str((run/'db').resolve()).casefold().encode()).hexdigest()
    windows=complete('test_inspect',args(action='windows',session_id=sid))
    wid=next(w['window_id'] for w in windows['data']['windows'] if 'Action Fixture' in w['title'])
    before=capture_tree(depth=20,max_nodes=1000)
    same=capture_tree(depth=20,max_nodes=1000)
    unchanged=diff_ui_snapshots(before,same)
    check('stable_ids_no_false_changes',unchanged['status']!='unavailable' and unchanged['counts']['changed']==0 and unchanged['counts']['removed']==0 and unchanged['counts']['added']==0,unchanged)
    selected=complete('test_action',args(action='select_page',session_id=sid,window={'id':wid},element={'selector':{'name':'Вторая'}}))
    assert selected.get('status')=='succeeded',selected
    after=capture_tree(depth=20,max_nodes=1000)
    changed=diff_ui_snapshots(before,after)
    check('page_visibility_change',any(c['property']=='visible' for n in changed['changed'] for c in n['changes']),changed)
    limited=capture_tree(depth=1,max_nodes=2)
    partial=diff_ui_snapshots(after,limited)
    check('truncated_no_false_deletion',partial['status']=='partial' and partial['removed']==[] and partial['counts']['unobserved_ids']>0,partial)
    foreign=deepcopy(after);foreign['binding']['generation']='other';foreign['binding']['window_id']='other'
    denied=diff_ui_snapshots(before,foreign)
    check('foreign_generation_refused',denied['status']=='unavailable' and denied['removed']==[],denied)
    captures=dict(before=before,same=same,after=after,limited=limited)
    (run/'captures.json').write_text(json.dumps(captures,ensure_ascii=False,indent=2),encoding='utf-8')
    (run/'provenance.json').write_text(json.dumps(dict(platform=version,mode='file-http',base_id=base_id,
        epf_sha256=hashlib.sha256(toolkit_epf.read_bytes()).hexdigest(),fixture_sha256=hashlib.sha256(fixture_epf.read_bytes()).hexdigest(),
        comparator_sha256=hashlib.sha256((root/'onec_mcp_toolkit_proxy/ui_snapshot_diff.py').read_bytes()).hexdigest(),
        synthetic_check='foreign_generation_refused modifies binding of live capture; not a platform restart'),indent=2),encoding='utf-8')
    print(json.dumps({'run':str(run),'passed':sum(c['ok'] for c in checks),'checks':len(checks)}))
finally:
    for process in reversed(owned):stop(process)
    (run/'cleanup.json').write_text(json.dumps({'owned':[p.pid for p in owned],'all_exited':all(p.poll() is not None for p in owned)}),encoding='utf-8')
