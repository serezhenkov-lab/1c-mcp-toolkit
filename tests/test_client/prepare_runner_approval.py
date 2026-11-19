"""Isolated manager dialog driver; no product or tested-client adapter."""
from pathlib import Path
import shutil,re
root=Path(__file__).resolve().parents[2]
out=root/'.local/runner-approval-20261117'
shutil.copytree(root/'1c/MCPToolkit',out/'toolkit')
shutil.copytree(root/'tests/test_client/action_fixture',out/'fixture')
(out/'db').mkdir()
shutil.copy2(root/'.local/runner-refusal-20261117/db/1Cv8.1CD',out/'db/1Cv8.1CD')
p=out/'fixture/ApiFixture/Forms/Main/Ext/Form/Module.bsl'
s=p.read_text(encoding='utf-8-sig');needle='Процедура ТекстПриИзменении(Элемент)\nКонецПроцедуры'
assert s.count(needle)==1
p.write_text(s.replace(needle,'Процедура ТекстПриИзменении(Элемент)\n    Результат = Строка(Число(Результат) + 1);\nКонецПроцедуры'),encoding='utf-8-sig')
p=out/'toolkit/MCPToolkit/Forms/Форма/Ext/Form/Module.bsl';s=p.read_text(encoding='utf-8-sig')
m=re.search(r'Функция ЗапроситьРазрешениеТестирования\(.*?КонецФункции',s,re.S);assert m
old=m.group();new=old.replace('Возврат ОткрытьФорму(', 'ТестФормаРазрешения = ОткрытьФорму(')
new=new.replace('КонецФункции','''    ТестЗапросРазрешения = Команда.params.args.request_id;
    ПодключитьОбработчикОжидания("ТестРешениеRunner", 0.25, Истина);
    Возврат ТестФормаРазрешения;
КонецФункции''')
s='&НаКлиенте\nПерем ТестФормаРазрешения;\n&НаКлиенте\nПерем ТестЗапросРазрешения;\n'+s.replace(old,new)
s+='''
&НаКлиенте
Процедура ТестРешениеRunner()
    Если Не ТестФормаРазрешения.Открыта() Тогда Возврат; КонецЕсли;
    ФайлРешения = Новый Файл("@PATH@/decision.txt");
    Если ФайлРешения.Существует() Тогда
        ТекстРешения = Новый ТекстовыйДокумент;
        ТекстРешения.Прочитать(ФайлРешения.ПолноеИмя, КодировкаТекста.UTF8);
        Если ТекстРешения.ПолучитьСтроку(1) = ТестЗапросРазрешения Тогда
            ТестФормаРазрешения.Закрыть(ТекстРешения.ПолучитьСтроку(2) = "allow");
            Возврат;
        КонецЕсли;
    КонецЕсли;
    ПодключитьОбработчикОжидания("ТестРешениеRunner", 0.25, Истина);
КонецПроцедуры
'''.replace('@PATH@',out.as_posix())
p.write_text(s,encoding='utf-8-sig');print(out)
