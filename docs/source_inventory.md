# Проверка исходных материалов

Архив прочитан: 17 файлов, контроль ZIP пройден. HTML содержит полную исходную сцену. Найдены 83 отметки, 9 нелокализованных/внешних мест, 50 дорог, 44 подписи, 3070 векторных элементов, 4 печатных вида, 7 открытых источников и первичный текст.

Исходные файлы и SHA-256 перечислены в `data/baseline.json`. EPUB, извлечённый текст романа и исследовательские промежуточные файлы не входят в приложение. Источники и ссылки на главы/параграфы перенесены в БД.

Состав исходного архива:

- `Derry_Source_Package/README.md`
- `Derry_Source_Package/requirements.txt`
- `Derry_Source_Package/build/verify_interactive.cjs`
- `Derry_Source_Package/build/make_data.py`
- `Derry_Source_Package/build/make_notes.py`
- `Derry_Source_Package/build/make_interactive.py`
- `Derry_Source_Package/build/make_maps.py`
- `Derry_Source_Package/build/extract_book.py`
- `Derry_Source_Package/build/interactive_template.html`
- `Derry_Source_Package/output/maps/derry_central.svg`
- `Derry_Source_Package/output/maps/derry_barrens.svg`
- `Derry_Source_Package/output/maps/derry_data.json`
- `Derry_Source_Package/output/maps/derry_city.svg`
- `Derry_Source_Package/output/maps/derry_camp.svg`
- `Derry_Source_Package/validation/geometry_and_pdf_checks.json`
- `Derry_Source_Package/validation/interactive_check.json`
- `Derry_Source_Package/validation/label_audit.json`

Начальная сцена перенесена без изменений географической реконструкции. Старые JSON/SVG/HTML не используются как параллельные источники после загрузки. Для справки сохранён исходный исследовательский PDF, который не является актуализируемым экспортом БД.
