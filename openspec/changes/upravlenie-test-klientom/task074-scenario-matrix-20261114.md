# Матрица сценариев TASK-017 / 7.4

Актуальный остаток после TASK-022: [единая сводка](remaining-after-task022.md); новый локальный TI-05 на нативной форме — [протокол](native-document-partial.md). Таблица ниже сохраняет исторический статус на 14.11, не текущую полноту реализации.

Сверка всех **70 сценариев** трёх спецификаций на 14.11.2026. Полной приёмки нет. «Локально» означает доказательство только локального поведения в указанном протоколе; «частично» — проверена лишь часть условия; «не проверено» — требуемого доказательства нет; «документально» — зафиксирована граница, не исполнение. Исторические прогоны не объявляются свежими. Все маршруты и типы базы в совокупности не приняты.

Текущие локальные результаты — 7.3; исторические — соответствующие TASK. Каждый протокол содержит ссылки на сырые отчёты. [Машиночитаемая матрица и SHA-256 требований](evidence/task074-scenario-matrix.json).

| ID | Сценарий | Статус | Доказательство и предел проверки |
| --- | --- | --- | --- |
| TI-01/1 | Потерян ответ после записи | не проверено | [task061-readiness.md](task061-readiness.md) — Потеря ответа после записи и дедупликация общего lifecycle не выполнены. |
| TI-01/2 | Конфликт ключа | не проверено | [task061-readiness.md](task061-readiness.md) — Отказ публичного входа не является проверкой request_conflict. |
| TI-01/3 | Исход неизвестен | частично | [task073-partial.md](task073-partial.md) — unknown проверен локально при сбое добавления; транспортный исход записи не проверен. |
| TI-02/1 | Эквивалентные интерфейсы | не проверено | [task073-partial.md](task073-partial.md) — Обязательная матрица публичных маршрутов 0/6. |
| TI-02/2 | Сервер без клиентского контекста | частично | [task062-partial.md](task062-partial.md) — Локальный серверный dispatcher/ASGI отказывает; работающий server_host через сеть не проверен. |
| TI-03/1 | Запрет изменения | локально | [task073-partial.md](task073-partial.md) — document: deny, deny_no_effect, deny_input; действия не вызываются. |
| TI-03/2 | Сеансовое разрешение | локально | [task073-partial.md](task073-partial.md) — document: session_no_dialog; session-fixed/recover: permission_reset. Диалогами управляет harness. |
| TI-03/3 | Разовое согласие для составного ввода | локально | [task073-partial.md](task073-partial.md) — document: once_covers_input_steps, once_not_reused; не транспортная приёмка. |
| TI-03/4 | Отзыв перед исполнением из очереди | локально | [task073-partial.md](task073-partial.md) — document: revoked, queue_rechecked; policy: deny_before_dispatch. |
| TI-03/5 | Запоздалое сеансовое согласие | локально | [task073-partial.md](task073-partial.md) — document: stale_cannot_allow_session, late_cannot_allow_session. |
| TI-03/6 | Анонимизированные данные | частично | [task063-partial.md](task063-partial.md) — Python-политика вложенных данных и ID проверена; сквозной inspect/встроенная анонимизация не приняты. |
| TI-04/1 | Снимок клиента | не проверено | [task064-partial.md](task064-partial.md) — Положительного снимка test_client нет; PNG менеджера его не заменяет. |
| TI-04/2 | Недоступное окно | локально | [task064-partial.md](task064-partial.md) — Явный screenshot_target_unavailable без подмены; фактическая привязка клиентской цели не реализована. |
| TI-05/1 | Документ с исправлением ошибки | частично | [task073-partial.md](task073-partial.md) — 45 проверок служебной fixture; один документ подтверждён запросом. Нативная форма, маршруты и автономность не приняты. |
| TI-05/2 | Неполная матрица | документально | [task073-partial.md](task073-partial.md) — Приёмка явно неполная, 0/6; непроведённые среды перечислены. |
| TI-06/1 | Неверный тип параметра | локально | [task072-verification.md](task072-verification.md) — Python test_transport_contract проверяет схему типов; не положительный сквозной UI-вызов. |
| TI-06/2 | Первая версия запущена на 8.3 | не проверено | [preflight.md](preflight.md) — Исторический API-прототип 8.3 не подтверждает текущий контракт Toolkit v1 на 8.3. |
| TI-06/3 | Обращение к операции из другого контекста | не проверено | [task061-readiness.md](task061-readiness.md) — Общий lifecycle и изоляция operation_id между контекстами не подключены. |
| TI-07/1 | Новая документация при прежнем стенде | документально | [capabilities-851.md](capabilities-851.md) — Версии и исторические пробы разделены; runtime на 8.5.4 не выполнялся. |
| TI-07/2 | Неподдержанное действие | частично | [task044-preconditions.md](task044-preconditions.md) — Проверен отказ click_group до мутации; полная runtime-матрица capabilities/status не принята. |
| TS-01/1 | Запуск без режима менеджера | частично | [task073-partial.md](task073-partial.md) — session/result-normal: no_manager для start; отдельный attach без TESTMANAGER этим прогоном не доказан. |
| TS-01/2 | Второй клиент | локально | [task073-partial.md](task073-partial.md) — session-fixed: second_start, no_second_after_detach; recover: restart_no_duplicate. |
| TS-01/3 | Подключение другой базы | локально | [task073-partial.md](task073-partial.md) — session-fixed: other_database; отказ иному профилю, не успешное подключение второй базы. |
| TS-01/4 | Предупреждение открытия внешней обработки | частично | [preflight.md](preflight.md) — Историческое предупреждение внешней обработки наблюдалось; полный отказ текущего Toolkit по тайм-ауту не проверен. |
| TS-02/1 | Долгий запуск | частично | [task073-partial.md](task073-partial.md) — Локальный start/status проверен; неблокирующий публичный транспорт и длительный естественный старт не приняты. |
| TS-02/2 | Ошибка запуска | локально | [task073-partial.md](task073-partial.md) — session-fixed: zero_timeout, timeout_no_retry; проверен ограниченный локальный отказ. |
| TS-03/1 | Отключение | частично | [task073-partial.md](task073-partial.md) — detach и сохранение процесса проверены; все UI-команды после detach отдельно не прогонялись. |
| TS-03/2 | Чужой процесс | локально | [task073-partial.md](task073-partial.md) — foreign_stop_denied; recover restart_stop_denied. |
| TS-03/3 | Совпадение порта | локально | [task073-partial.md](task073-partial.md) — port_is_not_ownership, foreign_attached, foreign_stop_denied. |
| TS-03/4 | Остановка собственного клиента | локально | [task073-partial.md](task073-partial.md) — stop_started, stop_confirmed; остановка только своего тестового процесса. |
| TS-04/1 | Перезапуск менеджера во время действия | частично | [task073-partial.md](task073-partial.md) — Локальный recover, сброс разрешения, старый session_id и явная pending-инъекция; штатный сетевой restart не проверен. |
| TS-04/2 | Потеря связи | частично | [task073-partial.md](task073-partial.md) — connection_lost и disconnect после таблицы; полный набор последующих UI-команд не принят. |
| UI-01/1 | Неоднозначный элемент | локально | [task073-partial.md](task073-partial.md) — ui: ambiguous; отказ неоднозначной цели без произвольного выбора. |
| UI-01/2 | Устаревшее окно | локально | [task073-partial.md](task073-partial.md) — ui: stale_window, stale_element. |
| UI-01/3 | Две одновременные команды | локально | [task073-partial.md](task073-partial.md) — ui: queued, status_during_queue, serial_order; локальная очередь. |
| UI-01/4 | Активное окно не определено | не проверено | [task013-runtime.md](task013-runtime.md) — Отдельный случай active=Неопределено при непустом списке окон не подтверждён отчётом. |
| UI-02/1 | Открытие ссылки | частично | [task073-partial.md](task073-partial.md) — ui: open/windows_after для ApiFixture; препятствие при открытии ссылки отдельно не подтверждено. |
| UI-02/2 | Чтение сообщений | локально | [task073-partial.md](task073-partial.md) — ui: messages_available/messages_preserved; снимки текущих сообщений. |
| UI-02/3 | Ограничение дерева | локально | [task073-partial.md](task073-partial.md) — ui: depth_truncated, nodes_truncated, coverage_partial. |
| UI-03/1 | Проверяемый ввод | локально | [task041-runtime.md](task041-runtime.md) — text_readback, check_boolean, choice_complete в историческом локальном прогоне; tabular choice не принят. |
| UI-03/2 | Очистка текстового поля | локально | [task041-runtime.md](task041-runtime.md) — clear_readback; свежий document также вводит пустое поле. |
| UI-03/3 | Неоднозначная форма выбора | частично | [task041-runtime.md](task041-runtime.md) — Неоднозначный список отклонён; выбор через табличную форму не реализован. |
| UI-03/4 | Значение отклонено формой | локально | [task041-runtime.md](task041-runtime.md) — rejected/rejected_actual; фактическое значение после обработчика. |
| UI-03/5 | Неполный поиск значения | частично | [task041-runtime.md](task041-runtime.md) — Усечённый список: list_incomplete/incomplete_not_selected; табличная форма не принята. |
| UI-03/6 | Неизвестный исход ввода | локально | [task041-runtime.md](task041-runtime.md) — unknown_no_fallback/readback_no_retry; редактор не отменяется. |
| UI-04/1 | Отказ записи документа | локально | [task073-partial.md](task073-partial.md) — document: save_call_not_save_result, required_message, unique_after_refusal. |
| UI-04/2 | Закрытие изменённой формы | локально | [task042-runtime.md](task042-runtime.md) — close_dialog, close_not_confirmed, dialog_returned, dialog_answer_separate. |
| UI-04/3 | Ошибка диагностики после действия | локально | [task042-runtime.md](task042-runtime.md) — diagnostic_failure/diagnostic_no_retry; инъекция ошибки после действия. |
| UI-04/4 | Наблюдение после нажатия кнопки | локально | [task042-runtime.md](task042-runtime.md) — click_once/click_scope/click_message; подтверждение ограничено вызовом и наблюдением. |
| UI-04/5 | Панель сообщений закрыта | частично | [task042-runtime.md](task042-runtime.md) — Недоступность сообщений описана контрактом; отдельный свежий прогон закрытой панели не подтверждён. |
| UI-05/1 | Изменение порядка строк | не проверено | [task051-without-adapter.md](task051-without-adapter.md) — Сортировка и повторная проверка позиционной цели не приняты. |
| UI-05/2 | Добавление и заполнение | частично | [task052-partial.md](task052-partial.md) — Пустая строка добавляется, редактирование остаётся pending; подтверждённого заполнения/row_id нет. |
| UI-05/3 | Частичное заполнение | частично | [task073-partial.md](task073-partial.md) — Сбои после add/readback/disconnect отражают шаги; частичное заполнение нескольких ячеек не проверено. |
| UI-05/4 | Удаление строки | не проверено | [task052-partial.md](task052-partial.md) — Подтверждённое адресное удаление строки не реализовано. |
| UI-05/5 | Отказ завершения редактирования | частично | [task052-partial.md](task052-partial.md) — row_edit_pending и сохранение редактора проверены; завершение строки недоступно на этом пути. |
| UI-05/6 | Одинаковые значения соседних строк | частично | [task051-without-adapter.md](task051-without-adapter.md) — Разные выделенные строки с одинаковыми описаниями не объединяются; полнота обхода не доказана. |
| UI-05/7 | Чтение требует навигации | частично | [task051-without-adapter.md](task051-without-adapter.md) — Без разрешения навигации — ограничение; разрешённый полный обход и восстановление курсора не приняты. |
| UI-05/8 | Недоступное массовое чтение таблицы | локально | [task051-without-adapter.md](task051-without-adapter.md) — Чтение только текущего выделения, неполнота явно указана; отсутствующий массовый метод не вызывается. |
| UI-06/1 | Сообщение в текущем снимке | локально | [task073-partial.md](task073-partial.md) — ui: expect_message/message_absent, messages_preserved. |
| UI-06/2 | Строка без навигации | частично | [task035-runtime.md](task035-runtime.md) — Навигации нет, но положительное совпадение не подтверждается без независимой идентичности: incomplete_search. |
| UI-06/3 | Отсутствие строки не доказано | локально | [task073-partial.md](task073-partial.md) — ui: row_absence, row_switched_not_confirmed; отсутствие не объявляется доказанным. |
| UI-06/4 | Условие достигнуто | локально | [task073-partial.md](task073-partial.md) — ui: eventually/expect; условие достигнуто после передачи управления платформе. |
| UI-06/5 | Тайм-аут | локально | [task073-partial.md](task073-partial.md) — ui: zero, queue_wait; ограниченное ожидание без повторного действия. |
| UI-07/1 | Нажатие карточки | не проверено | [task044-donors.md](task044-donors.md) — Успешное click_group не реализовано; отказ capability не закрывает сценарий. |
| UI-07/2 | Открытие значения ячейки | не проверено | [capabilities-851.md](capabilities-851.md) — 1.4/5.4 открыты; исследование открытия значения не возобновлялось. |
| UI-07/3 | Метод доступен, но результат открытия не подтверждён | частично | [capabilities-851.md](capabilities-851.md) — Историческое расхождение зафиксировано; публичная операция не принята, новых проб нет. |
| UI-07/4 | Неподдержанная область inspect | локально | [task073-partial.md](task073-partial.md) — ui: *_unsupported_command_interface/command_bars/table_additions; неполнота не подменяется пустотой. |
| UI-08/1 | Две одинаковые строки | частично | [task073-partial.md](task073-partial.md) — ui: row_duplicates_not_confirmed и row_distinct_physical_rows; адресный выбор одинаковых строк не реализован. |
| UI-08/2 | Смена строки между чтениями | локально | [task073-partial.md](task073-partial.md) — ui: row_switched_not_confirmed/switch_count; одинаковые тексты не подтверждают целостность. |
| UI-08/3 | Идентичность требует навигации | частично | [task051-without-adapter.md](task051-without-adapter.md) — expect/read без разрешения не навигируют; разрешённое независимое доказательство/обход не приняты. |
