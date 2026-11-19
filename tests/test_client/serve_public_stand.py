import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
file_mode = '--file' in sys.argv
run = root / ('.local/queue1-file' if file_mode else '.local/queue1')
port = 17656 if file_mode else 17655
os.environ.update(OPERATION_JOURNAL_DIR=str(run / 'journal'), PORT='17655',
                  ANONYMIZATION_ENABLED='false', FILE_BRIDGE_ROOT='')
if file_mode:
    os.environ.update(FILE_BRIDGE_ROOT=str(run / ('bridge-final' if '--fresh-bridge' in sys.argv else 'bridge')),
                      FILE_BRIDGE_CHANNELS='queue1', PORT=str(port))
from onec_mcp_toolkit_proxy.server import app
import uvicorn

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning')
