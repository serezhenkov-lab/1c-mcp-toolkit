# TASK-013/3.4 — coverage inspect

Добавлен coverage в результат внутреннего клиентского исполнителя test_inspect. Каждый элемент содержит scope/status/reason.

- tree: form_tree complete либо partial по фактическим complete/reason обхода, включая depth/max_nodes.
- windows: complete только для списка окон; form_tree partial/not_requested.
- values: complete только для запрошенных targets, partial при недоступном значении; form_tree partial/not_requested.
- messages: complete только для текущего снимка сообщений, partial при недоступности; form_tree partial/not_requested.
- command_interface, command_bars, table_additions: всегда unsupported/adapter_not_implemented. Это отсутствие адаптера, не утверждение об отсутствии элементов или методов платформы.

Существующие complete/truncated не расширяют охват до всего интерфейса. Coverage включается в проверку размера ответа; при ошибке после начала наблюдения возвращается partial с доступной причиной, а не complete. Формат прежних данных сохранён; новый coverage — дополнительное поле. Синхронный отказ при валидации до постановки команды в очередь не является снимком inspect и не получает coverage.

## Проверка

Одноразовая копия Toolkit `.local/task034/run2`, изолированная файловая база controlled85, ApiProbe, Windows/тонкий клиент 8.5.1.1529. Рабочая установка не обновлялась.

Платформенная проверка ThinClient/Server/HandlersExistence и сборка тестовой EPF успешны. [Runtime: 70/70 утверждений](evidence/task034-runtime.json), включая 24 новых проверки coverage: три unsupported-области для шести сценариев, complete для дерева и выбранных областей, partial при ограничении глубины/числа узлов. Сохранены прежние 46 проверок UI, очереди, ожиданий, сообщений и селекторов.

[BSL LS](evidence/task034-static.json): один изменённый модуль, 308 диагностик, Error=0; статус findings, не чистый анализ. Полный baseline-сравнительный анализ не проводился. Python не менялся, его регрессия отдельно не запускалась. Ветви недоступности values/messages, ошибки до наблюдения и лимит 1 МиБ покрыты кодом, но отдельный fault-injection runtime в этом прогоне не выполнялся.

Публичные транспорты и интеграционная приёмка остаются TASK-016/017. Пункт 1.4 открыт, исследование Открыть() не продолжалось. Пункт 3.5 и идентичность строк не изменены.
