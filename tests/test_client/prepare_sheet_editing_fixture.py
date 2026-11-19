"""Prepare an isolated spreadsheet-document field for native editing acceptance."""
from pathlib import Path
import shutil,sys
root=Path(__file__).resolve().parents[2];out=Path(sys.argv[1]).resolve()
assert out.is_relative_to(root/'.local')
shutil.copytree(root/'tests/test_client/action_fixture',out,dirs_exist_ok=True)
p=out/'ApiFixture/Forms/Main/Ext/Form/Module.bsl';s=p.read_text(encoding='utf-8-sig');old='Текст = "Начальное"; Результат = "0";'
assert s.count(old)==1
s=s.replace(old,old+'''
    РеквизитыПробы = Новый Массив;
    РеквизитыПробы.Добавить(Новый РеквизитФормы("ТабДок", Новый ОписаниеТипов("ТабличныйДокумент")));
    ИзменитьРеквизиты(РеквизитыПробы);
    ДокументПробы = Новый ТабличныйДокумент;
    ДокументПробы.Область(1, 1).Текст = "SHEET_EDITING_UNCHANGED";
    ЭтаФорма.ТабДок = ДокументПробы;
    ПолеПробы = Элементы.Добавить("ТабДок", Тип("ПолеФормы"));
    ПолеПробы.Вид = ВидПоляФормы.ПолеТабличногоДокумента;
    ПолеПробы.ПутьКДанным = "ТабДок";
    ПолеПробы.Редактирование = Истина;
    ПолеПробы.Защита = Ложь;
    ПолеПробы.ТолькоПросмотр = Ложь;
''');p.write_text(s,encoding='utf-8')
