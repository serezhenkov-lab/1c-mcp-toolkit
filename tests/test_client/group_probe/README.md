# Диагностика предусловий click_group

Проба API менеджера на 8.5.1.1529; не реализация click_group и не клиентский адаптер.
Создаёт три группы с известными из XML свойствами, читает доступные свойства
через ТестируемаяГруппаФормы и однократно вызывает Нажать() с независимым счётчиком.
Положительное `ok` в сырых записях означает, что наблюдение сохранено; наличие
свойства и исход вызова находятся в details.available/details.invoked.

Подготовка из корня проекта, в новые каталоги:

```powershell
Copy-Item tests/test_client/action_fixture .local/task044/fixture -Recurse
python tests/test_client/prepare_runtime.py .local/task044/run1 --action
python tests/test_client/group_probe/prepare.py .local/task044/run1 .local/task044/fixture
```

Собрать fixture/ApiFixture.xml в run1/InputFixture.epf и run1/MCPToolkit.xml в
run1/Toolkit-test.epf обычным epf-build с платформенной проверкой.
Запускать через tests/test_client/run_runtime.ps1 с -RunDir и явно выбранной
одноразовой -DatabasePath. Транспортный порт 16538 должен быть свободен.
Используется ЗаписьJSON существующего harness, не ТекстовыйДокумент.Записать.
Открыть() ячейки и клиентский адаптер не используются.
