"""A real public restart while a nonblocking UI expectation is in flight."""
import json
from pathlib import Path
import time
import uuid
import httpx

run = Path(__file__).resolve().parents[2] / '.local/queue1'
c = httpx.Client(base_url='http://127.0.0.1:17655', timeout=90)
events = []


def call(tool, args):
    result = c.post('/api/' + tool + '?channel=queue1', json=args).json()
    events.append(dict(tool=tool, args=args, result=result))
    (run / 'interrupted-probe.json').write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def poll(identifier):
    return call('test_session', dict(request_id=str(uuid.uuid4()), action='status',
                                    params={'operation_id': identifier}))['data']['operation']


prior = json.loads((run / 'restart-probe.json').read_text(encoding='utf-8'))
attached = next(e['result']['data']['operation'] for e in prior
                if e.get('tool') == 'test_session' and e['result'].get('data', {}).get('operation', {}).get('request_id') == 'restart-attach'
                and e['result']['data']['operation']['status'] == 'succeeded')
sid = attached['session_id']
windows = call('test_inspect', dict(request_id='interrupted-windows', session_id=sid, action='windows', params={}))
for _ in range(40):
    if windows['status'] == 'succeeded':
        break
    time.sleep(.25)
    windows = poll(windows['operation_id'])
window = {'id': next(w['window_id'] for w in windows['data']['windows'] if w['active'])}
args = dict(request_id='interrupted-expect', session_id=sid, window=window, timeout_ms=60000,
            params={'condition': {'property': 'title', 'operator': 'equals', 'value': 'never-this-title'}})
waiting = call('test_expect', args)
time.sleep(1)
assert poll(waiting['operation_id'])['status'] == 'running'
restarted = call('restart_1c_session', {})
assert restarted['success'], restarted
for _ in range(30):
    result = poll(waiting['operation_id'])
    if result['status'] == 'unknown':
        break
    time.sleep(.25)
assert result['status'] == 'unknown', result
repeat = call('test_expect', args)
assert repeat['operation_id'] == waiting['operation_id'] and repeat['status'] == 'unknown', repeat
print('in-flight operation became unknown; repeat did not execute')
