"""Summarize evidence without turning known unmet assertions into passes."""
import ast
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[2]
run=root/'.local/queue1-acceptance'
summary={'routes':[], 'platform':'8.5.1.1529','database_mode':'file','acceptance_complete':False}
for route in ('http','file','embedded'):
    folder=run/route
    report=json.loads((folder/'acceptance.json').read_text(encoding='utf-8'))
    failed=[x['name'] for x in report['checks'] if not x['ok']]
    assert len(report['checks'])==23
    assert failed==(['interrupted_unknown','unknown_no_replay'] if route=='file' else []),failed
    restart=next(x for x in report['events'] if x['tool']=='restart_1c_session')
    contract=json.loads((folder/'contract-probe.json').read_text(encoding='utf-8'))
    assert sum(x['transport']=='mcp' for x in contract)==7
    assert sum(x['transport']=='rest' for x in contract)==70
    retention=json.loads((folder/'retention.json').read_text(encoding='utf-8'))
    assert retention[-1]['result']['error']['code']=='request_conflict'
    assert retention[-2]['result']['data']['operation']['error']['code']=='result_expired'
    assert retention[-3]['result']['operation_id']==retention[0]['result']['operation_id']
    assert retention[-3]['result']['error']['code']=='result_expired'
    summary['routes'].append(dict(route=route,passed=23-len(failed),failed=failed,
        restart_ms=restart['ms'],native_calls=7,rest_cases=70,retention_checks=4))
source=root/'1c/MCPToolkit/MCPToolkit/Forms/Форма/Ext/Form/Module.bsl'
summary['source_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
assert summary['source_sha256']=='bb5b420ffc94e2e7504044ec3cbab2d4aa99eba5b0812d8b30f6583d685ba352'
for script in (root/'tests/test_client').glob('*queue1*.py'):
    ast.parse(script.read_text(encoding='utf-8-sig'))
(run/'verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False))
