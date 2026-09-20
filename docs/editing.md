# Внесение исправлений

Все команды ниже выполняются из корня проекта. Для краткости в блоках используется `python manage.py`; в рабочем Compose предваряйте эту команду `docker compose exec web`. Для импорта локального файла сначала скопируйте его в контейнер, например `docker compose cp changes.json web:/app/var/changes.json`.

Начинайте с просмотра ID и активной версии:

```sh
python manage.py atlas history
python manage.py atlas show feature 12
python manage.py atlas show geometry g:12
```

## Название, пояснение, уверенность и координаты

```sh
python manage.py atlas edit 12 \
  --name 'Derry Public Library' --short 'Derry Public Library' \
  --description 'Position reviewed against chapter references; footprint remains inferred.' \
  --confidence B --x -1490 --y -505 \
  --author 'Developer' --reason 'Recheck library placement' --dry-run
```

Уберите `--dry-run`, чтобы применить. При необходимости добавьте `--expected-revision N`, где N получен из history. При несовпадении текущей версии команда ничего не запишет. X и Y задаются парой. Для нелокализованного объекта нельзя назначить случайную координату этой командой: его перевод в локализованный объект требует явного пакета с новым числовым ID и геометрией.

`--period` меняет период; `--name` без `--short` обновляет также краткое название. Имя обновляет связанные подписи с `follow_name`; специально отредактированное в том же пакете название подписи сохраняется. Геометрия корпусов хранится относительно якоря, поэтому её не надо перемещать отдельно.

## Источники и геометрия

```sh
python manage.py atlas edit 12 --sources /app/var/sources.json \
  --author 'Developer' --reason 'Update evidence'
python manage.py atlas edit road:01 --geometry /app/var/kansas.json \
  --author 'Developer' --reason 'Adjust street bend'
```

`sources.json` — массив объектов `source_id`, `reference`, необязательный `note`. Он заменяет весь набор связей источников выбранного объекта. `source_id` должен существовать; новый источник добавляется вместе со ссылкой через `atlas apply`. Пример с сохранёнными исходными ссылками библиотеки — `examples/library_sources.json`.

Файл `kansas.json` — полный объект shape, например `{"type":"line","points":[...]}`. Получите существующую геометрию через `atlas show geometry g:road:01`, исправьте вершины и передайте только поле shape. Двойные штрихи дороги пересчитаются вместе. Соседние иллюстративные здания остаются самостоятельными фигурами.

## Редактирование footprint, подписи, оформления, рельефа

```sh
python manage.py atlas export /app/var/current.json
python manage.py atlas apply /app/var/changes.json \
  --author 'Developer' --reason 'Geometry and label adjustment' --dry-run
python manage.py atlas apply /app/var/changes.json \
  --author 'Developer' --reason 'Geometry and label adjustment'
```

В экспортированном файле найдите components с `feature_id="12"`: у каждого есть ссылка geometry_id и style_id. Локальные точки их геометрии измеряются от якоря библиотеки. Не прибавляйте к ним абсолютные координаты второй раз. Для перемещения подписи измените dx/dy в label. У общей Style изменение применяется ко всем использующим её компонентам; для индивидуального оформления добавьте новую Style и переназначьте style_id выбранного Component в одной транзакции.

`examples/change_library.json` — минимальный пакет изменения описания; `examples/change_footprint.json` — пример реального существующего корпуса, его прямоугольник заменяется целиком; `examples/change_terrain.json` — полный набор параметров рельефа с изменённой амплитудой одного холма. Все примеры служат для проверки процедуры и **не являются утверждёнными исправлениями реконструкции**. Они не применяются при запуске приложения.

## Добавление и удаление

`examples/add_place.json` добавляет тестовый объект 84, его геометрию, небольшой footprint и источник одним пакетом. Используйте на тестовой копии, затем отредактируйте данные для реального объекта. Ключи прежних 83 объектов и U1…U9 не перенумеровываются.

```sh
python manage.py atlas apply /app/var/add_place.json \
  --author 'Developer' --reason 'Add reviewed place'
python manage.py atlas delete 84 --author 'Developer' --reason 'Remove example'
```

Удаление удаляет объект с его связанными надписями, компонентами и свидетельствами. История остаётся. Неиспользуемые geometry/style сохраняются, поскольку могут быть полезны для повторного применения; при необходимости удалите их отдельными операциями того же пакета. Используемый ресурс удалить нельзя.

## Экспорт, импорт, история и откат

```sh
python manage.py atlas export /app/var/current.json
python manage.py atlas validate /app/var/current.json
python manage.py atlas import /app/var/current.json \
  --author 'Developer' --reason 'Import reviewed complete dataset'
python manage.py atlas history --limit 30
python manage.py atlas rollback 1 --author 'Developer' --reason 'Return to initial map'
```

Импорт — полная замена карты текущим содержимым файла, включая настройки. Полный импорт и откат сохраняют краткие подписи и тексты надписей ровно из снимка; автоматическое переименование применяется только к edit и частичному пакету apply. Одинаковый снимок не создаёт лишнюю ревизию. Откат восстанавливает состояние **после** указанной ревизии и фиксируется новой записью; это не удаление истории и не выборочный undo одного объекта. Для отмены только части исправлений используйте явный пакет с прежними значениями.

Полный дамп PostgreSQL отличается от JSON-экспорта: он содержит историю, состояние и таблицу миграций. Перед большой заменой полезно сделать `sh scripts/backup.sh`.

## Фотографии

Фотографии живут вне журнала ревизий атласа (см. architecture.md). Файлы в каталог media руками не кладутся: команда `photos` сохраняет оригинал, считает SHA-256 (повторная загрузка того же файла отклоняется), генерирует миниатюру и средний размер и создаёт запись в БД.

Рабочий процесс: скопировать оригиналы на сервер (`scp`/`rsync` во временную папку, затем `docker compose cp` в контейнер) и добавить по одному:

```sh
docker compose cp photo.png web:/tmp/photo.png
python manage.py photos add /tmp/photo.png \
  --caption 'Derry Public Library: the stone adult building.' \
  --feature 12 --year 1958 --character ben-hanscom --tag library
```

`--feature` — существующий ключ из таблицы feature; фото может быть и без места. `--year` проверяется по справочнику эпох романа (`ALLOWED_YEARS` в `atlas/photos.py`). Персонажи и теги — слаги (строчные буквы, цифры, дефисы); отсутствующие записи справочников создаются на лету, имя персонажа выводится из слага (`ben-hanscom` → `Ben Hanscom`).

Партия из десятков фото — каталог с манифестом, применяется атомарно (все или ни одной):

```sh
docker compose cp ./photos-batch web:/tmp/photos-batch
python manage.py photos import /tmp/photos-batch   # ищет manifest.json рядом с файлами
```

Манифест — JSON-список объектов: `file` (имя в каталоге), необязательные `caption`, `feature`, `year`, `characters`, `tags`, `order`.

Просмотр и правка атрибутов (файлы не трогаются): `photos list`, `photos show 3`, `photos edit 3 --caption '...' --feature ''` (пустая строка отвязывает), `--tag`/`--character` заменяют весь набор, `--no-tags`/`--no-characters` очищают. `photos remove 3` удаляет запись вместе с файлами.

После правок атласа, удаляющих места, выполните `photos check`: команда сообщит висячие привязки, отсутствующие и ничейные файлы.

## Обновление сайта и экспорта

После commit обновите страницу сайта. Для предварительной сборки используйте `atlas rebuild`. PNG рельефа и векторная сцена вычисляются из одной версии. Затем `atlas render --output /app/var/exports` создаёт PDF/SVG актуальной карты; manifest.json содержит номер версии и хеш. Самостоятельное редактирование выгруженного SVG не возвращает изменения в БД.

Печатный макет рассчитан на исходную плотность карты. При чрезмерном увеличении количества объектов или длины кратких названий команда сообщит переполнение индекса; она не станет молча выкидывать места. Для крупного расширения разработчик должен адаптировать печатную компоновку.
