"""Local isolated proxy; record executor lifecycle events without changing them."""
import json
import os
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
run = root / '.local/lifecycle-approval'
os.environ.update(OPERATION_JOURNAL_DIR=str(run / 'journal'), PORT='17654',
                  ANONYMIZATION_ENABLED='false', FILE_BRIDGE_ROOT='')
if '--file' in sys.argv:
    os.environ.update(OPERATION_JOURNAL_DIR=str(run / 'journal-file'), FILE_BRIDGE_ROOT=str(run / 'bridge'),
                      FILE_BRIDGE_CHANNELS='lifecycle-approval')
from onec_mcp_toolkit_proxy.server import app
import uvicorn

async def audit_app(scope, receive, send):
    async def receive_audit():
        message = await receive()
        if scope['type'] == 'http' and scope['path'] == '/1c/result' and message.get('body'):
            with (run / 'responses.jsonl').open('a', encoding='utf-8') as f:
                f.write(message['body'].decode('utf-8-sig') + '\n')
        return message
    await app(scope, receive_audit, send)

if __name__ == '__main__':
    uvicorn.run(audit_app, host='127.0.0.1', port=17654, log_level='warning')
