#!/usr/bin/env python3
"""Regenerate table dictionary and editable/viewable ER documents from Django models."""
import os,sys,html
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from atlas import models as m
from atlas.dataset import TABLES
root=Path(__file__).resolve().parents[1];docs=root/'docs'
models=list(TABLES.values())+[m.Revision,m.MapState,m.Character,m.Tag,m.Photo,m.Photo.characters.through,m.Photo.tags.through]
meaning={'Setting':'Настройки методологии, рельефа, палитры и печати. Структуры JSON описаны в data_interface.md и initial.json.',
'Geometry':'Исходные фигуры в локальных метрических координатах; абсолютные либо локальные для relative-компонентов.',
'Feature':'Смысловые объекты, включая 83 исходные отметки и U1…U9.',
'Style':'Переиспользуемые цвета, толщина, штрихи и слой.',
'Component':'Привязка фигуры/рецепта отрисовки к объекту, геометрии и стилю.',
'Label':'Фоновые подписи с привязкой к объекту или собственной позицией.',
'Source':'Библиографические записи и открытые веб-источники.',
'Evidence':'Связь объекта с источником, главой/параграфом и пояснением.',
'MapView':'Охваты и масштаб четырёх видов city, central, barrens, camp.',
'Revision':'Неизменяемый журнал полных снимков before/after и контрольного хеша.',
'MapState':'Одна строка id=1: признак первичной загрузки и активная версия.',
'Character':'Справочник персонажей для фотографий; пополняется командой photos.',
'Tag':'Свободные теги фотографий; создаются на лету при загрузке.',
'Photo':'Фотографии: отдельный контур вне ревизий атласа. Файлы в media по SHA-256, производные размеры thumb/medium.',
'Photo_characters':'Связь многие-ко-многим фото — персонаж.',
'Photo_tags':'Связь многие-ко-многим фото — тег.'}
notes={'key':'Стабильный первичный ключ.','value':'JSON-параметры; схема зависит от key.','shape':'Фигура point/line/poly/rect/circle.','object_type':'site/unplaced/road/water/area/path/rail/landmark/decoration.','name':'Полное название; у декоративной неназванной улицы может быть пустым.','short':'Краткая подпись отметки.','kind':'Категория отметки или тип дороги.','confidence':'A/B/C для отметки, U для unplaced, пусто для базовой геометрии.','rank':'Приоритет отображения: 1, 2 или 3.','period':'Периоды/даты как текст.','note':'Пояснение или оговорка.','metadata':'Дополнительные данные происхождения, исходный индекс, хеш источника.','z':'Порядок отрисовки, неотрицательное число.','recipe':'Способ построения фигуры: relative, smooth, slice, generator.','text':'Текст фоновой подписи; пустой берёт имя Feature.','dx':'Метрическое смещение X или абсолютная X для несвязанной подписи.','dy':'Метрическое смещение Y или абсолютная Y для несвязанной подписи.','spec':'Шрифт/размер/угол/класс/виды, follow_name и web_offset.','title':'Название источника/вида.','url':'HTTP(S)-ссылка; у EPUB пусто.','role':'Для чего использован источник.','paragraph':'Номер параграфа данной EPUB-экстракции, не страница. Null для других ссылок.','reference':'Глава, интерлюдия или другая проверяемая ссылка.','order':'Порядок ссылок в карточке.','subtitle':'Подзаголовок печатного листа.','scale':'Знаменатель масштаба A2, положительное число.','bounds':'[xmin,ymin,xmax,ymax] в метрах.','created':'UTC дата и время создания версии.','author':'Указанное разработчиком имя автора.','reason':'Причина изменений.','before':'Полный снимок перед правкой.','after':'Полный снимок после правки.','digest':'SHA-256 канонического after-снимка.','id':'Числовой PK; у MapState всегда 1.','initialized':'Seed был успешно применён; последующие запуски его пропускают.',
'slug':'Слаг: строчные латинские буквы, цифры, дефисы.','sha256':'SHA-256 содержимого оригинала; определяет имена файлов и защищает от дублей.','ext':'Расширение оригинала: png, jpg или webp.','original_name':'Имя загруженного файла, для справки.','caption':'Подпись фотографии.','width':'Ширина оригинала в пикселях.','height':'Высота оригинала в пикселях.',
'feature_key':'Строковый ключ Feature, намеренно без FK: commit атласа полностью заменяет строки feature, и каскад стирал бы привязки. Проверяется photos.py и `photos check`.'}
lines=['# Словарь таблиц и полей','', 'SQL имена приведены для PostgreSQL. JSONField хранится как jsonb. Обязательность относится к NULL; пустые строки/словари проверяются правилами приложения. FK защищены ссылочной целостностью, on_delete описывает поведение Django.','']
mer=['erDiagram','    direction TB']
for model in models:
 name=model.__name__;lines += [f'## `{model._meta.db_table}` — {name}', '',meaning[name],'','| Поле | Тип | NULL | Назначение |','|---|---|---|---|']
 mer.append('    '+name+' {')
 for f in model._meta.fields:
  typ=f.get_internal_type()
  if f.is_relation:
   ty=f'FK → {f.related_model._meta.db_table}.{f.target_field.name}'
   desc='Связь; on_delete='+f.remote_field.on_delete.__name__+'.'
  else:
   ty={'CharField':f'varchar({f.max_length})','TextField':'text','JSONField':'jsonb','BooleanField':'boolean','FloatField':'double precision','PositiveSmallIntegerField':'smallint ≥ 0','PositiveIntegerField':'integer ≥ 0','BigAutoField':'bigint identity','DateTimeField':'timestamptz','URLField':f'varchar({f.max_length})'}.get(typ,typ)
   desc=notes.get(f.name,'Служебное поле.')
   if name=='Source' and f.name=='kind':desc='novel или web.'
   if name=='Character' and f.name=='name':desc='Имя персонажа для показа.'
   if name=='Photo' and f.name=='order':desc='Порядок в галерее и карточке места.'
   if name=='Photo' and f.name=='created':desc='UTC время загрузки.'
   if name=='Photo' and f.name=='year':desc='Год эпохи романа или null; справочник ALLOWED_YEARS в atlas/photos.py.'
  if f.primary_key:desc='PK. '+desc
  lines.append(f'| `{f.column}` | {ty} | {"да" if f.null else "нет"} | {desc} |')
  marker=' PK' if f.primary_key else (' FK' if f.is_relation else '')
  mer.append(f'        {"json" if typ=="JSONField" else "string" if typ in ("CharField","URLField","TextField") or f.is_relation else "number" if "Integer" in typ or typ in ("BigAutoField","FloatField") else "boolean" if typ=="BooleanField" else "datetime"} {f.column}{marker}')
 mer.append('    }');lines.append('')
 for f in model._meta.fields:
  if f.is_relation:
   mer.append(f'    {f.related_model.__name__} '+('|o' if f.null else '||')+('--o| ' if name=='MapState' else '--o{ ')+name+f' : "{f.column}"')
lines+=['## Ограничения','', '- PK уникальны; FK не допускают висячих ссылок.','- Ранг объекта 1–3; уверенность A/B/C/U или пустая для базовых объектов.','- Unplaced имеет null geometry и U; остальные объекты требуют geometry.','- Масштаб положителен. Единственная строка MapState имеет id=1.','- Подробная проверка геометрии, ссылок, цветов, параметров и структуры JSON выполняется `atlas validate` и автоматически до любой поддерживаемой записи.','- Имена SQL-ограничений и индексы приведены в schema.sql.']
(docs/'data_dictionary.md').write_text('\n'.join(lines)+'\n');(docs/'er.mmd').write_text('\n'.join(mer)+'\n')
# The SVG is intentionally self-contained and editable in a vector editor.
boxes={
 'Geometry':(30,150,['PK key','shape · jsonb']), 'Feature':(440,150,['PK key','FK geometry_id ?','name · short · kind','confidence · period · note']),
 'Style':(860,20,['PK key','value · jsonb']), 'Component':(860,250,['PK key','FK feature_id ?','FK geometry_id ?','FK style_id · z · recipe']),
 'Source':(30,480,['PK key','title · url · role']), 'Evidence':(440,480,['PK key','FK feature_id','FK source_id','paragraph · reference']),
 'Label':(860,510,['PK key','FK feature_id ?','text · dx · dy · spec']),
 'Revision':(30,760,['PK id','created · author · reason','before · after · digest']), 'MapState':(440,760,['PK id = 1','FK revision_id ?','initialized']),
 'Setting':(860,760,['PK key','value · jsonb']), 'MapView':(440,1000,['PK key','title · subtitle','bounds · scale']),
 'Photo':(30,1000,['PK id','sha256 · ext · caption','feature_key (строка, не FK)','year · order · width · height']),
 'Character':(30,1240,['PK slug','name']), 'Tag':(440,1240,['PK slug'])}
W,H=280,140
edges=[('Geometry','Feature',[(310,205),(440,205)]),('Geometry','Component',[(170,290),(170,390),(1000,390)]),('Feature','Component',[(720,235),(790,235),(790,300),(860,300)]),('Style','Component',[(1000,160),(1000,250)]),('Feature','Evidence',[(580,290),(580,480)]),('Source','Evidence',[(310,550),(440,550)]),('Feature','Label',[(720,190),(1190,190),(1190,565),(1140,565)]),('Revision','MapState',[(310,830),(440,830)]),('Photo','Character',[(120,1140),(120,1240)]),('Photo','Tag',[(250,1140),(250,1200),(560,1200),(560,1240)])]
s=['<svg xmlns="http://www.w3.org/2000/svg" width="1220" height="1460" viewBox="0 0 1220 1460">','<rect width="1220" height="1460" fill="#f6f3e9"/>','<style>text{font-family:DejaVu Sans,sans-serif;fill:#263d38}.title{font-size:20px;font-weight:bold}.field{font-size:15px}.edge{fill:none;stroke:#75867b;stroke-width:2}</style>','<text x="30" y="38" class="title">Derry — database relationships</text>','<text x="30" y="69" class="field">PK: primary key · FK: foreign key · ?: nullable · 1 → many (MapState: at most one)</text>','<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto"><path d="M0 0L10 5L0 10" fill="none" stroke="#75867b"/></marker></defs>']
for a,b,pts in edges:
 s.append('<polyline class="edge" points="'+' '.join(f'{x},{y}' for x,y in pts)+'" marker-end="url(#arrow)"/>')
for name,(x,y,fields) in boxes.items():
 s.append(f'<g id="{name}"><rect x="{x}" y="{y}" width="{W}" height="{H}" rx="8" fill="#ffffff" stroke="#9aaa98"/><text x="{x+14}" y="{y+27}" class="title">{name}</text>')
 for i,line in enumerate(fields):s.append(f'<text x="{x+14}" y="{y+53+i*23}" class="field">{html.escape(line)}</text>')
 s.append('</g>')
s+=['<text x="30" y="1415" class="field">Setting and MapView have no relational foreign keys; JSON references are validated by the application.</text>','<text x="30" y="1442" class="field">Full field definitions: data_dictionary.md · Editable relationship source: er.mmd</text>','<text x="750" y="1295" class="field">Photo — Character and Photo — Tag are many-to-many</text>','<text x="750" y="1322" class="field">(link tables photo_characters, photo_tags).</text>','<text x="750" y="1349" class="field">photo.feature_key is an app-validated string, not an FK:</text>','<text x="750" y="1376" class="field">atlas commits fully replace feature rows.</text>','</svg>']
(docs/'er.svg').write_text('\n'.join(s))
print('Updated data_dictionary.md, er.mmd, er.svg')
