"""Fault injection around real /1c/result; bind localhost only."""
import asyncio
import json
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
run = root / '.local/lifecycle'
os.environ['OPERATION_JOURNAL_DIR'] = str(run / 'journal')
os.environ['PORT'] = '17653'
os.environ['ANONYMIZATION_ENABLED'] = 'false'
os.environ['FILE_BRIDGE_ROOT'] = ''
from onec_mcp_toolkit_proxy.server import app
from starlette.responses import JSONResponse
import uvicorn


async def fault_app(scope, receive, send):
    if scope['type'] == 'http' and scope['path'] == '/1c/result':
        messages = []
        body = b''
        while True:
            message = await receive()
            messages.append(message)
            body += message.get('body', b'')
            if not message.get('more_body'):
                break
        text = body.decode('utf-8', errors='replace')
        if 'LIFECYCLE_DROP' in text and not (run / 'dropped-result.json').exists():
            (run / 'dropped-result.json').write_bytes(body)
            await JSONResponse({'success': True, 'test_dropped_after_execution': True})(scope, receive, send)
            return
        if 'LIFECYCLE_LATE' in text and not (run / 'delayed-result.json').exists():
            (run / 'delayed-result.json').write_bytes(body)
            await asyncio.sleep(3)
        async def replay():
            if messages:
                return messages.pop(0)
            return await receive()
        await app(scope, replay, send)
    else:
        await app(scope, receive, send)


if __name__ == '__main__':
    uvicorn.run(fault_app, host='127.0.0.1', port=17653, log_level='warning')
