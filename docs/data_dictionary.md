# Словарь таблиц и полей

SQL имена приведены для PostgreSQL. JSONField хранится как jsonb. Обязательность относится к NULL; пустые строки/словари проверяются правилами приложения. FK защищены ссылочной целостностью, on_delete описывает поведение Django.

## `atlas_setting` — Setting

Настройки методологии, рельефа, палитры и печати. Структуры JSON описаны в data_interface.md и initial.json.

| Поле | Тип | NULL | Назначение |
|---|---|---|---|
| `key` | varchar(100) | нет | PK. Стабильный первичный ключ. |
| `value` | jsonb | нет | JSON-параметры; схема зависит от key. |

## `atlas_geometry` — Geometry

Исходные фигуры в локальных метрических координатах; абсолютные либо локальные для relative-компонентов.

| Поле | Тип | NULL | Назначение |
|---|---|---|---|
| `key` | varchar(100) | нет | PK. Стабильный первичный ключ. |
| `shape` | jsonb | нет | Фигура point/line/poly/rect/circle. |

## `atlas_feature` — Feature

Смысловые объекты, включая 83 исходные отметки и U1…U9.

| Поле | Тип | NULL | Назначение |
|---|---|---|---|
| `key` | varchar(100) | нет | PK. Стабильный первичный ключ. |
| `object_type` | varchar(20) | нет | site/unplaced/road/water/area/path/rail/landmark/decoration. |
| `name` | varchar(300) | нет | Полное название; у декоративной неназванной улицы может быть пустым. |
| `short` | varchar(150) | нет | Краткая подпись отметки. |
| `kind` | varchar(40) | нет | Категория отметки или тип дороги. |
| `confidence` | varchar(1) | нет | A/B/C для отметки, U для unplaced, пусто для базовой геометрии. |
| `rank` | smallint ≥ 0 | нет | Приоритет отображения: 1, 2 или 3. |
| `period` | varchar(200) | нет | Периоды/даты как текст. |
| `note` | text | нет | Пояснение или оговорка. |
| `geometry_id` | FK → atlas_geometry.key | да | Связь; on_delete=PROTECT. |
| `metadata` | jsonb | нет | Дополнительные данные происхождения, исходный индекс, хеш источника. |

## `atlas_style` — Style

Переиспользуемые цвета, толщина, штрихи и слой.

| Поле | Тип | NULL | Назначение |
|---|---|---|---|
| `key` | varchar(100) | нет | PK. Стабильный первичный ключ. |
| `value` | jsonb | нет | JSON-параметры; схема зависит от key. |

## `atlas_component` — Component

Привязка фигуры/рецепта отрисовки к объекту, геометрии и стилю.

| Поле | Тип | NULL | Назначение |
|---|---|---|---|
| `key` | varchar(100) | нет | PK. Стабильный первичный ключ. |
| `feature_id` | FK → atlas_feature.key | да | Связь; on_delete=CASCADE. |
| `geometry_id` | FK → atlas_geometry.key | да | Связь; on_delete=PROTECT. |
| `style_id` | FK → atlas_style.key | нет | Связь; on_delete=PROTECT. |
| `z` | integer ≥ 0 | нет | Порядок отрисовки, неотрицательное число. |
| `recipe` | jsonb | нет | Способ построения фигуры: relative, smooth, slice, generator. |

## `atlas_label` — Label

Фоновые подписи с привязкой к объекту или собственной позицией.

| Поле | Тип | NULL | Назначение |
|---|---|---|---|
| `key` | varchar(100) | нет | PK. Стабильный первичный ключ. |
| `feature_id` | FK → atlas_feature.key | да | Связь; on_delete=CASCADE. |
| `text` | varchar(300) | нет | Текст фоновой подписи; пустой берёт имя Feature. |
| `dx` | double precision | нет | Метрическое смещение X или абсолютная X для несвязанной подписи. |
| `dy` | double precision | нет | Метрическое смещение Y или абсолютная Y для несвязанной подписи. |
| `spec` | jsonb | нет | Шрифт/размер/угол/класс/виды, follow_name и web_offset. |

## `atlas_source` — Source

Библиографические записи и открытые веб-источники.

| Поле | Тип | NULL | Назначение |
|---|---|---|---|
| `key` | varchar(100) | нет | PK. Стабильный первичный ключ. |
| `title` | varchar(500) | нет | Название источника/вида. |
| `kind` | varchar(20) | нет | novel или web. |
| `url` | varchar(2000) | нет | HTTP(S)-ссылка; у романа пусто. |
| `role` | text | нет | Для чего использован источник. |
| `metadata` | jsonb | нет | Дополнительные данные происхождения, исходный индекс, хеш источника. |

## `atlas_evidence` — Evidence

Связь объекта с источником, главой и пояснением.

| Поле | Тип | NULL | Назначение |
|---|---|---|---|
| `key` | varchar(100) | нет | PK. Стабильный первичный ключ. |
| `feature_id` | FK → atlas_feature.key | нет | Связь; on_delete=CASCADE. |
| `source_id` | FK → atlas_source.key | нет | Связь; on_delete=PROTECT. |
| `reference` | text | нет | Глава, интерлюдия или другая проверяемая ссылка. |
| `note` | text | нет | Пояснение или оговорка. |
| `order` | integer ≥ 0 | нет | Порядок ссылок в карточке. |

## `atlas_mapview` — MapView

Охваты и масштаб четырёх видов city, central, barrens, camp.

| Поле | Тип | NULL | Назначение |
|---|---|---|---|
| `key` | varchar(100) | нет | PK. Стабильный первичный ключ. |
| `title` | varchar(150) | нет | Название источника/вида. |
| `subtitle` | varchar(300) | нет | Подзаголовок печатного листа. |
| `scale` | integer ≥ 0 | нет | Знаменатель масштаба A2, положительное число. |
| `bounds` | jsonb | нет | [xmin,ymin,xmax,ymax] в метрах. |

## `atlas_revision` — Revision

Неизменяемый журнал полных снимков before/after и контрольного хеша.

| Поле | Тип | NULL | Назначение |
|---|---|---|---|
| `id` | bigint identity | нет | PK. Числовой PK; у MapState всегда 1. |
| `created` | timestamptz | нет | UTC дата и время создания версии. |
| `author` | varchar(150) | нет | Указанное разработчиком имя автора. |
| `reason` | text | нет | Причина изменений. |
| `before` | jsonb | нет | Полный снимок перед правкой. |
| `after` | jsonb | нет | Полный снимок после правки. |
| `digest` | varchar(64) | нет | SHA-256 канонического after-снимка. |

## `atlas_mapstate` — MapState

Одна строка id=1: признак первичной загрузки и активная версия.

| Поле | Тип | NULL | Назначение |
|---|---|---|---|
| `id` | smallint ≥ 0 | нет | PK. Числовой PK; у MapState всегда 1. |
| `initialized` | boolean | нет | Seed был успешно применён; последующие запуски его пропускают. |
| `revision_id` | FK → atlas_revision.id | да | Связь; on_delete=PROTECT. |

## `atlas_character` — Character

Справочник персонажей для фотографий; пополняется командой photos.

| Поле | Тип | NULL | Назначение |
|---|---|---|---|
| `slug` | varchar(100) | нет | PK. Слаг: строчные латинские буквы, цифры, дефисы. |
| `name` | varchar(150) | нет | Имя персонажа для показа. |

## `atlas_tag` — Tag

Свободные теги фотографий; создаются на лету при загрузке.

| Поле | Тип | NULL | Назначение |
|---|---|---|---|
| `slug` | varchar(100) | нет | PK. Слаг: строчные латинские буквы, цифры, дефисы. |

## `atlas_photo` — Photo

Фотографии: отдельный контур вне ревизий атласа. Файлы в media по SHA-256, производные размеры thumb/medium.

| Поле | Тип | NULL | Назначение |
|---|---|---|---|
| `id` | bigint identity | нет | PK. Числовой PK; у MapState всегда 1. |
| `sha256` | varchar(64) | нет | SHA-256 содержимого оригинала; определяет имена файлов и защищает от дублей. |
| `ext` | varchar(8) | нет | Расширение оригинала: png, jpg или webp. |
| `original_name` | varchar(255) | нет | Имя загруженного файла, для справки. |
| `caption` | text | нет | Подпись фотографии. |
| `year` | smallint ≥ 0 | да | Год эпохи романа или null; справочник ALLOWED_YEARS в atlas/photos.py. |
| `feature_key` | varchar(100) | нет | Строковый ключ Feature, намеренно без FK: commit атласа полностью заменяет строки feature, и каскад стирал бы привязки. Проверяется photos.py и `photos check`. |
| `order` | integer ≥ 0 | нет | Порядок в галерее и карточке места. |
| `width` | integer ≥ 0 | нет | Ширина оригинала в пикселях. |
| `height` | integer ≥ 0 | нет | Высота оригинала в пикселях. |
| `created` | timestamptz | нет | UTC время загрузки. |

## `atlas_photo_characters` — Photo_characters

Связь многие-ко-многим фото — персонаж.

| Поле | Тип | NULL | Назначение |
|---|---|---|---|
| `id` | bigint identity | нет | PK. Числовой PK; у MapState всегда 1. |
| `photo_id` | FK → atlas_photo.id | нет | Связь; on_delete=CASCADE. |
| `character_id` | FK → atlas_character.slug | нет | Связь; on_delete=CASCADE. |

## `atlas_photo_tags` — Photo_tags

Связь многие-ко-многим фото — тег.

| Поле | Тип | NULL | Назначение |
|---|---|---|---|
| `id` | bigint identity | нет | PK. Числовой PK; у MapState всегда 1. |
| `photo_id` | FK → atlas_photo.id | нет | Связь; on_delete=CASCADE. |
| `tag_id` | FK → atlas_tag.slug | нет | Связь; on_delete=CASCADE. |

## Ограничения

- PK уникальны; FK не допускают висячих ссылок.
- Ранг объекта 1–3; уверенность A/B/C/U или пустая для базовых объектов.
- Unplaced имеет null geometry и U; остальные объекты требуют geometry.
- Масштаб положителен. Единственная строка MapState имеет id=1.
- Подробная проверка геометрии, ссылок, цветов, параметров и структуры JSON выполняется `atlas validate` и автоматически до любой поддерживаемой записи.
- Имена SQL-ограничений и индексы приведены в schema.sql.
