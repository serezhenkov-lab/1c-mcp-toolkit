"""Modal regression; see run_modal_capture.py for the shared stand harness."""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).with_name('run_modal_capture.py')), run_name='__main__')
