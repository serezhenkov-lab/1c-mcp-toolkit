"""Direct embedded HTTP acceptance consumer. Never launches a proxy or retries a mutation."""
from pathlib import Path
import json, sys, time, uuid
import httpx

RUN = Path(__file__).resolve().parents[2] / '.local/http-mvp'
HTTP = httpx.Client(base_url='http://127.0.0.1:17825', timeout=45, trust_env=False)


def save(name, data):
    path = RUN / (name + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def send(tool, arguments):
    response = HTTP.post('/api/' + tool, json=arguments)
    response.raise_for_status()
    return response.json()


def call(tag, tool, arguments, *, wait=True):
    # Save the exact durable request before first delivery. Unknown never causes a resend.
    if (RUN / (tag + '-request.json')).exists():
        raise RuntimeError('Request tag already exists; inspect its operation before continuing: ' + tag)
    arguments = {'request_id': 'mvp-' + uuid.uuid4().hex, 'params': {}, **arguments}
    save(tag + '-request', {'tool': tool, 'arguments': arguments})
    result = send(tool, arguments)
    save(tag + '-accepted', result)
    if wait:
        deadline = time.monotonic() + 150
        while result.get('status') in ('queued', 'running', 'awaiting_approval'):
            if time.monotonic() > deadline:
                raise TimeoutError(('Observe existing operation; do not retry', result))
            time.sleep(.35)
            receipt = send('test_session', dict(request_id='status-' + uuid.uuid4().hex,
                           action='status', params={'operation_id': result['operation_id']}))
            result = receipt.get('data', {}).get('operation', result)
            save(tag + '-result', result)
    save(tag + '-result', result)
    return result


def flatten(nodes):
    for node in nodes:
        yield node
        yield from flatten(node.get('children', []))


if __name__ == '__main__':
    tag, tool, argument_file = sys.argv[1:4]
    result = call(tag, tool, json.loads(Path(argument_file).read_text(encoding='utf-8-sig')),
                  wait='--no-wait' not in sys.argv)
    print(json.dumps(result, ensure_ascii=False, indent=2))
