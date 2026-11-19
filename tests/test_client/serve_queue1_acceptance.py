"""Proxy owner for an isolated route; never reads working-install configuration."""
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
route = sys.argv[1]
assert route in ('http', 'file')
run = Path(os.environ.get('TOOLKIT_QUEUE1_ROOT', str(root / '.local/queue1-acceptance'))) / route
port = 17665 if route == 'http' else 17666
os.environ.update(OPERATION_JOURNAL_DIR=str(run / 'journal'), PORT=str(port),
                  ANONYMIZATION_ENABLED='false', FILE_BRIDGE_ROOT='', FILE_BRIDGE_CHANNELS='')
if route == 'file':
    os.environ.update(FILE_BRIDGE_ROOT=str(run / 'bridge'), FILE_BRIDGE_CHANNELS='queue1')
from onec_mcp_toolkit_proxy.server import app
import uvicorn
uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning')
