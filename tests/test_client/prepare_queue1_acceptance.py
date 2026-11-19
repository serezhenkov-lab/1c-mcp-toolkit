"""Fresh three-route stands, reusing the trusted embedded fixture only for setup."""
from pathlib import Path
import subprocess
import sys
import shutil
import os

root = Path(__file__).resolve().parents[2]
for route, port, client_port in [('http', 17665, 16545), ('file', 17666, 16546), ('embedded', 17667, 16547)]:
    if len(sys.argv)>1 and route not in sys.argv[1:]:continue
    run = Path(os.environ.get('TOOLKIT_QUEUE1_ROOT', str(root / '.local/queue1-acceptance'))).resolve() / route
    assert run.is_relative_to(root / '.local')
    assert not run.exists(), 'Preserve previous evidence'
    (run / 'db').mkdir(parents=True)
    # Source is an idle disposable database. Copy only its primary database file.
    shutil.copy2(root / '.local/queue1/db/1Cv8.1CD', run / 'db/1Cv8.1CD')
    subprocess.run([sys.executable, '-B', str(root / 'tests/test_client/prepare_embedded_stand.py'),
                    '--run', str(run), '--revision', 'epf-final', '--port', str(port),
                    '--client-port', str(client_port)], check=True)
    if route == 'embedded':
        continue
    path = run / 'epf-final/MCPToolkit/Forms/Форма/Ext/Form/Module.bsl'
    text = path.read_text(encoding='utf-8-sig')
    start = text.index('        НастроитьОбщийLifecycle(', text.index('Процедура ТестEmbeddedСтарт()'))
    end = text.index('        Профиль = ', start)
    text = text[:start] + text[end:]
    start = text.index('        РежимПодключения = 1;', text.index('Процедура ТестEmbeddedСтарт()'))
    end = text.index('        ПоследнееУправление', start)
    address = f'file://{run.as_posix()}/bridge/queue1' if route == 'file' else f'http://127.0.0.1:{port}'
    text = text[:start] + f'''        АдресСервера = "{address}";
        ИдентификаторКанала = "queue1"; РежимПодключения = 0;
        ИспользоватьТочнуюАнонимизацию = Ложь;
        Подключиться(Неопределено, Ложь);
''' + text[end:]
    path.write_text(text, encoding='utf-8-sig')
