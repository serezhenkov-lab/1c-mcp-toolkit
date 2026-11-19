"""Document-only reconciliation of saved evidence; never starts a test/runtime."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
CHANGE = ROOT / 'openspec/changes/upravlenie-test-klientom'
old = json.loads((CHANGE / 'evidence/task074-scenario-matrix-20261114.json').read_text(encoding='utf-8-sig'))
historical = {(r['requirement'], r['scenario']): r for r in old['scenarios']}
updates = {}

def update(ids, status, evidence, limitation, level='runtime_local'):
    for identifier in ids.split():
        updates[identifier] = dict(status=status, evidence=evidence, limitation=limitation, evidence_level=level)

update('TI-01/1', 'локально', 'lost-response.md', '60/60 сохранённых проверок на HTTP/file/embedded, файловая база: потерян ответ после UI-записи, один документ и тот же operation_id. Клиент-серверный режим не проверен.')
update('TI-01/2 TI-06/3', 'локально', 'queue1-current.md', 'Общий lifecycle: conflict/изоляция и публичные test_* подтверждены локальными протоколами HTTP/file/embedded. Это не полная средовая матрица.')
update('TI-01/3', 'локально', '../archive/2026-11-19-rezhimy-podtverzhdeniya-i-izolyatsiya-chatov/file-recovery.md', 'Unknown после UI commit подтверждён прежним queue1-finish; новый file recovery 17/17 сохраняет unknown и один документ. Legacy/unclaimed и другие среды открыты.')
update('TI-01a/1 TI-01a/2', 'локально', 'lifecycle-fast.md', 'Status существующей операции без admission, квоты, прежние ключи, conflict/изоляция проверены на отдельной файловой 8.5.1.1529 и локально. Политика анонимизации не принята.')
update('TI-02/1', 'частично', 'native-scenario-cleanup.md', 'Нативный TI-05 и очистка прошли на трёх маршрутах файловой базы, 48/48. Все действия/отказы и клиент-серверный режим этим не покрыты.')
update('TI-03/6', 'частично', 'task063-partial.md', 'Есть прежние локальные проверки политики данных. Положительная сквозная анонимизация отложена пользователем; не объявляется принятой.', 'local_tests')
update('TI-04/1 TI-04/2', 'частично', 'queue2-summary.md', 'Подтверждены обычный/модальный снимок клиента, PID/CreationDate, реальные неоднозначные HWND и отказы. Пересоздание основного HWND, RDP/server_host/Linux/клиент-серверный режим не приняты.')
update('TI-05/1', 'локально', 'native-scenario-cleanup.md', '48/48: штатная форма, отказ обязательности, исправление, один документ, адресная очистка 9→10→9 на HTTP/file/embedded. Без ручного controller. Только файловые базы.')
update('TI-05/2', 'документально', 'native-scenario-cleanup.md', 'Полная приёмка явно 0/6, несмотря на успешный основной сценарий на трёх файловых маршрутах.', 'document')
update('TS-02/1', 'частично', 'queue1-remaining-checks.md', 'Публичные start/status и status во время ожидания подтверждены на локальных маршрутах. Естественный длительный старт на всех средах отдельно не принят; профиль/restart дополнительно описаны в local-profile.md.')
update('TS-04/1', 'частично', 'queue1-finish.md', 'UI commit до результата и отсутствие повтора подтверждены; новый file recovery описан отдельно. Старые row/snapshot ID после restart зависят от независимой идентичности.')
update('TS-04/3 TS-04/4', 'локально', 'file-restart.md', 'Доставка управляющего restart при активном файловом запросе и отсутствие повторной публикации проверены на отдельном стенде. Не вся матрица аварий/сред.')
update('UI-01/1', 'локально', 'queue1-finish.md', '25 точных кандидатов ограничены 20 с truncated/путями; неоднозначность не разрешается выбором первого. Только проверенные типы/локальная среда.')
update('UI-01/2', 'локально', 'modal-input-investigation.md', 'Закрытый MessageBox отклонён как stale_target до вызова. Причина исчезновения окна в старом прогоне не доказана; защита не ослаблена.')
update('UI-02/1', 'частично', 'native-scenario-cleanup.md', 'Публичное открытие списка нативного документа подтверждено на трёх файловых маршрутах. Полный набор препятствий при открытии не принят.')
update('UI-02/2 UI-04/1', 'локально', 'native-scenario-cleanup.md', 'На трёх файловых маршрутах сообщение обязательности сохранено, запись после отказа отсутствует, после исправления ровно одна. Нажатие само по себе не считается фактом записи.')
update('UI-03/1', 'частично', 'native-scenario-cleanup.md', 'Нативный текст/дата с readback подтверждены на трёх маршрутах; список/флажок ранее локально. Полный табличный выбор не реализован.')
update('UI-03/6', 'локально', 'modal-input-investigation.md', 'После ввода блокирующее окно останавливает finish_edit до перевода фокуса; текст не вводится повторно. Поздняя гонка и исходный unknown в иных случаях остаются возможны.')
update('UI-04/3', 'локально', 'intermediate-progress.md', 'Сохранены подтверждённые шаги; инъекция отказа доставки progress не повторяет действие и не подменяет его результат. Полная матрица диагностики открыта.')
update('TE-01/1 TE-01/2 TE-01/3', 'частично', 'queue1-finish.md', 'Состояния процесса/стадии Connect, StartTimeMismatch и отказ ложному stop проверены; AccessDenied/гонка endpoint моделировались инъекциями. Реальные ACL и все среды не приняты.')
update('TE-02/1 TE-02/2 TE-02/4', 'частично', 'queue2-summary.md', 'Кандидаты, предки, editor поля/ячейки/колонки/списка и unavailable подтверждены на локальном стенде. Полная матрица типов/сред не выполнена.')
update('TE-02/3 TE-02/5', 'частично', 'intermediate-progress.md', 'Ошибки диагностики/progress не меняют действие; проверены чужой канал и бюджеты. Полная приёмка всех артефактов и анонимизация остаются открытыми.')
update('TE-03/1', 'локально', 'query-comparison-implementation.md', '17 тестовых методов включают 24 примера контракта: кратность, ключи, типы, лимиты. Это локальная проверка компаратора, не UI-идентичность.', 'local_tests')
update('TE-03/2 TE-03/3', 'частично', 'query-verification-runtime.md', 'Свежие query-проверки на 8.5.1.1529; source_failed/incomplete/partial UI не считаются пустым достоверным набором. UI-ветка и другие маршруты открыты.')
update('TE-04/1 TE-04/3 TE-04/4 TE-04/5', 'частично', 'scenario-runner-partial.md', 'Полный preflight/новые ID/unknown без повтора подтверждены ранее. Продуктовый контекст: 24 capability на HTTP/file/embedded файловой 8.5.1.1529; Восстановление успешного префикса runner проверено после реальной потери процесса на embedded/file/HTTP 8.5.1.1529; file/HTTP дополнительно 20/20, в lifecycle нет новых операций ввода. Потерянный receipt не повторяется. Recovery continue_observation: HTTP/file/embedded по 8/8, failed/skipped сохранены, мутация не отправляется. Обновление истёкшего контекста: file/HTTP/embedded по 2/2 шага и 8/8, один ввод без повтора; полномочия и план неизменны. Отказ после вызванного ввода: file/HTTP/embedded partial, recover/resume без повторов, счётчик 1; HTTP/embedded 11/11, file ошибка типа флага проверена офлайн без нового ввода (scenario-mutation-failure.md). Подтверждение: file 17/17 после решения, HTTP/embedded 18/18 с recovery во время ожидания; отказ без ввода, разрешение один раз, resume только чтения (scenario-approval.md). File свежий binding при awaiting_approval блокирован; сверка unknown, таблицы и остальные среды открыты.')
update('TE-04/2', 'частично', 'scenario-context-provider.md', 'Продуктовый поставщик/CLI: 11 новых локальных тестов, embedded 8/8, file 4/4, HTTP 4/4. Живая привязка, отдельная политика; расширение до 24 capability: добавлены наличие/состояние поля и строковый ввод/очистка; HTTP 4+7, embedded 11/11, file 10/11 (последнее чтение блокировано истечением контекста), editing обычного поля unavailable по виду; table_state и field_state табличного документа false/true/false приняты на file/HTTP/embedded по 13/13; обычное поле guard блокирует до отправки. Другие записи, расширение реестра и среды не приняты.')
update('TE-05/1', 'частично', 'ui-snapshot-diff-partial.md', '12 локальных тестов, три живых проверки снимков и одна подмена привязки. Нет продуктового сборщика поколений, полного пересоздания формы и табличного diff.')
update('TE-06/1 TE-06/2', 'частично', 'step-metrics-partial.md', '10 локальных тестов, API без сброса и 4 проверки runner на файловой 8.5.1.1529. Продуктовый reader/эпоха, единицы и реальные перекрытия/атрибуция не приняты.')

update('TE-04/6', 'локально', 'action-input-resolution.md', 'Native guard до/после и отказы подтверждены ранее. Action Fixture принята после исправления подготовки вкладок стенда: итоговая EPF/скрытый клиент, input+readback succeeded. Общие другие среды не приняты.')

specs, rows = [], []
for path in sorted((CHANGE / 'specs').glob('*/spec.md')):
    relative = path.relative_to(CHANGE).as_posix()
    raw = path.read_bytes()
    specs.append(dict(path=relative, sha256=hashlib.sha256(raw).hexdigest()))
    req = None
    index = 0
    for line in raw.decode('utf-8-sig').splitlines():
        if line.startswith('### Requirement: '):
            req = line.split()[2]
            index = 0
        elif line.startswith('#### Scenario: '):
            index += 1
            title = line.split(': ', 1)[1]
            identifier = f'{req}/{index}'
            previous = historical.get((req, title))
            assert previous or identifier in updates, ('unreviewed scenario', identifier, title)
            row = dict(previous or {})
            row.update(id=identifier, requirement=req, scenario=title, spec=relative,
                       scope='extensions' if req.startswith('TE-') else 'v1',
                       evidence_level='historical_local', reviewed_at='2026-11-17')
            row.update(updates.get(identifier, {}))
            row['evidence_sha256'] = hashlib.sha256((CHANGE / row['evidence']).read_bytes()).hexdigest()
            rows.append(row)
assert len({r['id'] for r in rows}) == len(rows)
assert not (set(updates) - {r['id'] for r in rows})
counts = dict(Counter(r['status'] for r in rows))
payload = dict(task='TASK-017/7.4', reviewed_at='2026-11-17', acceptance='incomplete',
               runtime_rerun=False, scenarioCount=len(rows), statuses=counts,
               scopeCounts=dict(Counter(r['scope'] for r in rows)), specs=specs, scenarios=rows,
               historical='task074-scenario-matrix-20261114.json')
(CHANGE / 'evidence/task074-scenario-matrix.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
lines = ['# Матрица сценариев TASK-017 / 7.4 — 17.11.2026', '',
         f'Сверены **{len(rows)} сценариев** четырёх актуальных спецификаций. Новых runtime-запусков нет. Источник — накопленные протоколы; уровни доказательства не смешиваются.', '',
         '«Локально» — сценарий подтверждён в ограниченной среде/локальных тестах, не во всей обязательной матрице. «Частично» — положительный объём неполон. «Не проверено» — нужного доказательства нет. «Документально» — только зафиксированная граница. Отказ неподдержанной операции не закрывает её положительный сценарий.', '',
         'Уровни: runtime_local — протокол живого стенда (может включать отдельно обозначенные инъекции); local_tests — локальные тесты без нового runtime; historical_local — сохранённое доказательство прежней матрицы, не перепроверенное на текущем бинарнике; document — документальная фиксация.', '',
         '[Исторические 70 сценариев](task074-scenario-matrix-20261114.md) сохранены. [JSON и хеши](evidence/task074-scenario-matrix.json). [Итог приёмки](task074-acceptance.md). Полная приёмка **0/6**, задачи **13/42**; это разные показатели.', '',
         'Охват: ' + '; '.join(f'{k}: {v}' for k,v in counts.items()) + '. Это не процент приёмки.', '']
for scope,title in [('v1','Исходная версия TS/UI/TI'),('extensions','Расширения TE — отдельный рубеж')]:
    selected = [r for r in rows if r['scope']==scope]
    lines += [f'## {title} — {len(selected)} сценариев', '', '| ID | Сценарий | Охват / уровень | Доказательство и остаток |', '|---|---|---|---|']
    for r in selected:
        lines.append(f"| {r['id']} | {r['scenario']} | {r['status']} / {r['evidence_level']} | [{r['evidence']}]({r['evidence']}) — {r['limitation']} |")
    lines.append('')
(CHANGE / 'task074-scenario-matrix.md').write_text('\n'.join(lines), encoding='utf-8')
print(json.dumps(dict(total=len(rows), scopes=payload['scopeCounts'], statuses=counts), ensure_ascii=True))
