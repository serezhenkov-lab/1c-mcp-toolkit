"""TASK-020/10.3: fresh query verification on a disposable 8.5.1.1529 copy.

Reuses the historical UI-created document; no UI write/retry/capture suite runs.
"""
from pathlib import Path
import hashlib
import json
import shutil
import sys
from copy import deepcopy
from datetime import datetime, timezone
import uuid

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / 'tests/test_client'))
from query_verification import verify_document_response

run_name = 'query-verification-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
stand_path = root / '.local' / run_name
assert not stand_path.exists(), 'Preserve existing evidence'
(stand_path / 'http/db').mkdir(parents=True)
source_db = root / '.local/lost-response/http/db/1Cv8.1CD'
with source_db.open('rb') as source:
    with (stand_path / 'http/db/1Cv8.1CD').open('wb') as dest:
        shutil.copyfileobj(source, dest)
toolkit_epf = root / '.local/queue2-final/Toolkit-production.epf'
historical = json.loads((root / '.local/lost-response/http/results.json').read_text(encoding='utf-8'))
document = next(c['evidence'][0] for c in historical['checks'] if c['name'] == 'one_committed_document_before_retry')

# Definitions only; do not execute earlier acceptance tests.
source = (root / 'tests/test_client/run_queue1_finish.py').read_text(encoding='utf-8')
prefix = source[:source.index('try:\n    barrier =')]
prefix = prefix.replace("'.local/queue1-finish'", repr('.local/' + run_name))
prefix = prefix.replace("17669", "17679")
prefix = prefix.replace("str(stand / 'Toolkit.epf')", "str(toolkit_epf)")
prefix = prefix.replace("ANONYMIZATION_ENABLED='false'", "ANONYMIZATION_ENABLED='false', RESPONSE_FORMAT='json'")
exec(compile(prefix, 'query_verification_helpers', 'exec'))


def utc():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


query_text = ('ВЫБРАТЬ Ссылка КАК ref, ОбязательноеПоле КАК marker, ПометкаУдаления КАК deleted '
              'ИЗ Документ.T43_Required ГДЕ ОбязательноеПоле = &Маркер')
params = {'Маркер': historical['marker']}
fingerprint = hashlib.sha256(json.dumps(dict(query=query_text, params={
    'Маркер': {'type': 'string', 'value': historical['marker']}}), ensure_ascii=False,
    sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
base_id = hashlib.sha256(str((run / 'db').resolve()).casefold().encode('utf-8')).hexdigest()
schema = [dict(name=n, type=t, null_policy='reject') for n,t in
          [('ref','reference'),('marker','string'),('deleted','boolean')]]
contract = dict(id='one-document-v1', base_id=base_id, query_fingerprint=fingerprint,
                data_policy_id='isolated-synthetic-stand', schema=schema, mode='bag', keys=[],
                order_basis=None, ignore_columns=[])
stamp = utc()
baseline = dict(source=dict(kind='baseline', base_id=base_id, query_fingerprint=fingerprint,
    data_policy_id=contract['data_policy_id'], read_id='historical-ui-commit-pinned-to-copy',
    operation_id=None, started_at=stamp, finished_at=stamp, status='success', coverage='complete',
    effective_limit=None, fidelity='exact', order_proven=False, normalization_error=None),
    schema=deepcopy(schema), rows=[[
        dict(type='reference',value=dict(object_type='ДокументСсылка.T43_Required', id=document['reference'], presentation=None)),
        dict(type='string',value=document['marker']), dict(type='boolean',value=False)]])
(run / 'baseline.json').write_text(json.dumps(dict(contract=contract,baseline=baseline),ensure_ascii=False,indent=2),encoding='utf-8')
provenance = dict(platform='8.5.1.1529', database_source=str(source_db.relative_to(root)),
    source_db_sha256=hashlib.sha256(source_db.read_bytes()).hexdigest(),
    copy_db_sha256=hashlib.sha256((run/'db/1Cv8.1CD').read_bytes()).hexdigest(),
    toolkit_sha256=hashlib.sha256(toolkit_epf.read_bytes()).hexdigest(),
    historical_marker=historical['marker'], historical_reference=document['reference'],
    new_ui_write=False, route='HTTP proxy', baseline_pinned_before_query=True)
(run / 'provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding='utf-8')


def verify(name, query=query_text, query_params=None, limit=10):
    started = utc()
    response = client.post('/api/execute_query', params={'channel':'queue1'},
        json=dict(query=query,params=params if query_params is None else query_params,limit=limit,include_schema=True))
    finished = utc()
    (run / (name+'-response.json')).write_text(response.text, encoding='utf-8')
    context = dict(base_id=base_id, query_fingerprint=fingerprint,
        data_policy_id=contract['data_policy_id'], read_id=str(uuid.uuid4()), operation_id=None,
        started_at=started, finished_at=finished, effective_limit=limit,
        fidelity='exact', order_proven=False, response_complete=response.status_code==200)
    # Fingerprint is computed from the actual sent request, not copied from baseline.
    context['query_fingerprint'] = hashlib.sha256(json.dumps(dict(query=query, params={
        k:dict(type='string',value=v) for k,v in (params if query_params is None else query_params).items()}),
        ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
    result = verify_document_response(response.text, contract=contract, baseline=baseline, context=context)
    (run/(name+'-verification.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result, context


try:
    proxy = start_proxy()
    manager = start_manager()
    ready()
    binding = code('Результат = СтрокаСоединенияИнформационнойБазы();', 'server')
    assert str((run/'db').resolve()).casefold().replace('\\','/') in str(binding).casefold().replace('\\','/'), binding
    version = code('Информация = Новый СистемнаяИнформация; Результат = Информация.ВерсияПриложения;', 'server')
    check('isolated_base_and_version', version == '8.5.1.1529', {'base_id':base_id,'version':version})
    result, context = verify('one-document')
    check('one_document_business_confirmed', result['business_confirmed'], result)
    limited, _ = verify('at-limit', limit=1)
    check('limit_not_business_confirmation', not limited['business_confirmed'] and limited['comparison']['reason']=='incomplete_source', limited)
    failed, _ = verify('query-failure', query='ВЫБРАТЬ Ссылка ИЗ Документ.T103_Missing')
    check('query_failure_not_empty_success', not failed['business_confirmed'] and failed['comparison']['reason']=='source_failed', failed)
    # New integration guards, no additional query or UI snapshot acquisition.
    wrong = dict(context, base_id='another-base')
    raw = (run/'one-document-response.json').read_text(encoding='utf-8')
    denied = verify_document_response(raw, contract=contract, baseline=baseline, context=wrong)
    check('foreign_base_not_confirmed', not denied['business_confirmed'] and denied['comparison']['reason']=='source_mismatch', denied)
    partial = dict(context,response_complete=False)
    denied = verify_document_response(raw,contract=contract,baseline=baseline,context=partial)
    check('partial_read_not_confirmed', not denied['business_confirmed'] and denied['comparison']['reason']=='incomplete_source',denied)
    from onec_mcp_toolkit_proxy.query_comparison import compare_query_results,normalize_query_result
    ui = normalize_query_result(json.loads(raw),context,contract)
    ui['source'].update(kind='ui_snapshot',coverage='partial')
    denied=compare_query_results(dict(version=1,contract=contract,expected=baseline,actual=ui))
    check('partial_ui_not_query_proof',denied['status']=='unavailable' and not denied['business_confirmed'],denied)
    print(json.dumps({'checks':len(checks),'passed':sum(c['ok'] for c in checks)}))
finally:
    for process in reversed(owned):
        stop(process)
    (run/'cleanup.json').write_text(json.dumps({'owned':[p.pid for p in owned],
        'all_exited':all(p.poll() is not None for p in owned)}),encoding='utf-8')
