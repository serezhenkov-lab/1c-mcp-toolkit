&НаКлиенте
Процедура ТестЗаписьМеждуШагами()
    Если ТестЛимитСлучай.name <> "mutation" Тогда Возврат; КонецЕсли;
    Если ТестЛимитОтчет = Неопределено Или ТестЛимитОтчет.rounds.Количество() = 0 Тогда Возврат; КонецЕсли;
    Если Не ТестЛимитОтчет.Свойство("interleavings") Тогда ТестЛимитОтчет.Вставить("interleavings", Новый Массив); КонецЕсли;
    Фаза = ОбщийLifecycle.compaction.phase;
    Если Фаза <> "write" И Фаза <> "verify" И Фаза <> "verify_again" И Фаза <> "commit" Тогда Возврат; КонецЕсли;
    Если ТестЛимитОтчет.interleavings.Найти(Фаза) <> Неопределено Тогда Возврат; КонецЕсли;
    ТестЛимитОтчет.interleavings.Добавить(Фаза);
    Если Фаза = "write" Тогда
        ТестЛимитОтчет.Вставить("mutation_id", ТестЛимитПринять("mutation"));
    ИначеЕсли Фаза = "verify" Тогда
        LifecycleСобытие("test", ТестЛимитОтчет.mutation_id, "awaiting_approval", 1);
    ИначеЕсли Фаза = "verify_again" Тогда
        LifecycleСобытие("test", ТестЛимитОтчет.mutation_id, "running", 2);
    Иначе
        Ответ = ВстроенныйКонвертLifecycle(Новый Структура("request_id", "mutation"), ТестЛимитОтчет.mutation_id);
        Ответ.status = "succeeded"; Ответ.data = Новый Структура("text", "INTERLEAVED_RESULT_PRESERVED");
        LifecycleЗавершить("test", ТестЛимитОтчет.mutation_id, Новый Структура("success,data", Истина, Ответ));
    КонецЕсли;
    ТестЛимитОтчет.Вставить("mutation_record", LifecycleПолучить("test", ТестЛимитОтчет.mutation_id));
    ТестЛимитСохранить();
КонецПроцедуры
