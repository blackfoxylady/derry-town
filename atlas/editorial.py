"""Human-friendly spreadsheet workflow for bilingual place copy.

The tracked JSON corpus is the publication source.  XLSX is an editing view of
that corpus, deliberately implemented with the standard library so production
does not need an office-file dependency.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re
import tempfile
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from django.conf import settings
from django.utils.text import slugify


CORPUS_FORMAT = 'derry.place-editorial.v1'
CORPUS_PATH = Path(settings.BASE_DIR) / 'data' / 'place_editorial.json'
GLOSSARY_PATH = Path(settings.BASE_DIR) / 'data' / 'proper_names_ru.json'
PLACE_TYPES = {'site', 'unplaced'}
FIELDS = (
    'about', 'confidence_explanation', 'note_ru', 'about_ru',
    'confidence_explanation_ru',
)
READY = 'готово'
HEADERS = (
    'ID', 'Ссылка', 'Название EN', 'Краткое описание EN', 'О месте EN',
    'Достоверность EN', 'Название RU', 'Краткое описание RU', 'О месте RU',
    'Достоверность RU', 'Статус', 'Комментарий редактора', 'Диагностика',
)
_LATIN_WORD = re.compile(r'[A-Za-z]{2,}')
_CELL_REF = re.compile(r'([A-Z]+)(\d+)')
_NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
       'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}


def load_corpus(path=CORPUS_PATH):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('format') != CORPUS_FORMAT or not isinstance(data.get('places'), dict):
        raise ValueError(f'Unsupported editorial corpus: {path}')
    return data


def load_glossary(path=GLOSSARY_PATH):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                                     delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
        temporary = handle.name
    os.replace(temporary, path)


def sync_document(doc, corpus=None):
    """Merge the tracked editorial fields into an atlas snapshot."""
    corpus = corpus or load_corpus()
    places = corpus['places']
    features = {str(row['key']): row for row in doc['tables']['feature']
                if row['object_type'] in PLACE_TYPES}
    missing = sorted(set(features) - set(places))
    if missing:
        raise ValueError(f'Editorial key mismatch; missing={missing}')
    for key, feature in features.items():
        entry = places[key]
        for field in FIELDS:
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValueError(f'{key}: {field} must be nonempty text')
        feature['about'] = entry['about']
        feature['confidence_explanation'] = entry['confidence_explanation']
        metadata = deepcopy(feature.get('metadata') or {})
        ru = deepcopy(metadata.get('ru') or {})
        ru.update(note=entry['note_ru'], about=entry['about_ru'],
                  confidence_explanation=entry['confidence_explanation_ru'])
        metadata['ru'] = ru
        feature['metadata'] = metadata
    return doc


def diagnostics(name, note, about, confidence):
    messages = []
    first = next((char for char in name if char.isalpha()), '')
    if first and first == first.lower():
        messages.append('название со строчной буквы')
    latin = sorted(set(_LATIN_WORD.findall('\n'.join((note, about, confidence)))),
                   key=str.casefold)
    if latin:
        preview = ', '.join(latin[:8])
        if len(latin) > 8:
            preview += f' (+{len(latin) - 8})'
        messages.append('латиница: ' + preview)
    return '; '.join(messages)


def editorial_rows(doc, corpus=None, glossary=None, base_url='https://derryfiles.space'):
    corpus = corpus or load_corpus()
    glossary = glossary or load_glossary()
    features = [row for row in doc['tables']['feature'] if row['object_type'] in PLACE_TYPES]

    def sort_key(feature):
        key = str(feature['key'])
        return (0, int(key)) if key.isdigit() else (1, key)

    rows = []
    for feature in sorted(features, key=sort_key):
        key = str(feature['key'])
        entry = corpus['places'][key]
        name_ru = entry['name_ru']
        slug = slugify(feature['name'])
        url = f'{base_url.rstrip("/")}/ru/places/{key.lower()}-{slug}/'
        issue = diagnostics(name_ru, entry['note_ru'], entry['about_ru'],
                            entry['confidence_explanation_ru'])
        rows.append((key, url, feature['name'], feature['note'], entry['about'],
                     entry['confidence_explanation'], name_ru, entry['note_ru'],
                     entry['about_ru'], entry['confidence_explanation_ru'],
                     'черновик', '', issue))
    return rows


def _col_name(number):
    result = ''
    while number:
        number, rest = divmod(number - 1, 26)
        result = chr(65 + rest) + result
    return result


def _cell(ref, value, style=0):
    value = '' if value is None else str(value)
    preserve = ' xml:space="preserve"' if value[:1].isspace() or value[-1:].isspace() else ''
    return (f'<c r="{ref}" t="inlineStr" s="{style}"><is><t{preserve}>'
            f'{escape(value)}</t></is></c>')


def _sheet(rows, widths, editable_columns=(), issue_column=None, freeze='A2', autofilter=True):
    xml_rows = []
    for row_number, values in enumerate(rows, 1):
        cells = []
        for column, value in enumerate(values, 1):
            style = 1 if row_number == 1 else 3 if column in editable_columns else 2
            if row_number > 1 and issue_column == column and value:
                style = 4
            cells.append(_cell(f'{_col_name(column)}{row_number}', value, style))
        height = ' ht="42" customHeight="1"' if row_number > 1 else ' ht="30" customHeight="1"'
        xml_rows.append(f'<row r="{row_number}"{height}>{"".join(cells)}</row>')
    cols = ''.join(f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
                   for index, width in enumerate(widths, 1))
    selection = (f'<pane ySplit="1" topLeftCell="{freeze}" activePane="bottomLeft" state="frozen"/>'
                 '<selection pane="bottomLeft"/>') if freeze else '<selection/>'
    filter_xml = (f'<autoFilter ref="A1:{_col_name(len(widths))}{len(rows)}"/>'
                  if autofilter and rows else '')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetViews><sheetView workbookViewId="0">{selection}</sheetView></sheetViews>'
            '<sheetFormatPr defaultRowHeight="15"/>'
            f'<cols>{cols}</cols><sheetData>{"".join(xml_rows)}</sheetData>{filter_xml}'
            '</worksheet>')


def export_xlsx(path, doc, revision, base_url='https://derryfiles.space'):
    rows = editorial_rows(doc, base_url=base_url)
    instructions = [
        ('Редакторская ведомость мест Дерри', 'Значение'),
        ('Снимок ревизии БД', revision),
        ('Сформировано, UTC', datetime.now(timezone.utc).isoformat(timespec='seconds')),
        ('Как работать', 'Правьте только жёлтые столбцы на листе «Места». Английские поля даны для сверки.'),
        ('Что публикуется', 'Только строки со статусом «готово». Остальные строки импорт не меняет.'),
        ('Проверка', 'Перед статусом «готово» устраните замечания в столбце «Диагностика». Буквы A/B/C/U допустимы.'),
        ('Название', 'Пишите с заглавной буквы; URL и английское название менять не нужно.'),
        ('Возврат файла', 'Сохраните файл как XLSX и передайте его для проверки и публикации.'),
    ]
    glossary = load_glossary()
    terms = [('Оригинал', 'Согласованное написание RU')]
    terms.extend(sorted(glossary.get('terms', {}).items(), key=lambda item: item[0].casefold()))
    places = [HEADERS, *rows]
    sheets = [
        _sheet(instructions, (30, 110), editable_columns=(), freeze=None, autofilter=False),
        _sheet(places, (9, 48, 32, 55, 80, 80, 35, 55, 80, 80, 14, 35, 48),
               editable_columns=(7, 8, 9, 10, 11, 12), issue_column=13),
        _sheet(terms, (40, 50), editable_columns=(2,)),
    ]
    content_types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        + ''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1, 4))
        + '</Types>')
    root_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>')
    workbook = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Инструкция" sheetId="1" r:id="rId1"/>'
        '<sheet name="Места" sheetId="2" r:id="rId2"/>'
        '<sheet name="Словарь" sheetId="3" r:id="rId3"/></sheets></workbook>')
    workbook_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + ''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, 4))
        + '<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        '</Relationships>')
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2"><font><sz val="10"/><name val="Calibri"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="10"/><name val="Calibri"/></font></fonts>'
        '<fills count="5"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF315E5A"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFFF2CC"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFF4CCCC"/><bgColor indexed="64"/></patternFill></fill></fills>'
        '<borders count="2"><border/><border><left style="thin"><color rgb="FFD9D9D9"/></left><right style="thin"><color rgb="FFD9D9D9"/></right><top style="thin"><color rgb="FFD9D9D9"/></top><bottom style="thin"><color rgb="FFD9D9D9"/></bottom></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="5"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyAlignment="1"><alignment wrapText="1" vertical="center"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="4" borderId="1" xfId="0" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '</styleSheet>')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', content_types)
        archive.writestr('_rels/.rels', root_rels)
        archive.writestr('xl/workbook.xml', workbook)
        archive.writestr('xl/_rels/workbook.xml.rels', workbook_rels)
        archive.writestr('xl/styles.xml', styles)
        for index, sheet in enumerate(sheets, 1):
            archive.writestr(f'xl/worksheets/sheet{index}.xml', sheet)
    return len(rows)


def _cell_value(cell, shared):
    cell_type = cell.get('t')
    if cell_type == 'inlineStr':
        return ''.join(node.text or '' for node in cell.findall('.//m:t', _NS))
    value = cell.findtext('m:v', default='', namespaces=_NS)
    if cell_type == 's' and value:
        return shared[int(value)]
    return value


def read_xlsx_rows(path):
    path = Path(path)
    if path.stat().st_size > 10_000_000:
        raise ValueError('Редакторская книга превышает 10 МБ.')
    with ZipFile(path) as archive:
        for item in archive.infolist():
            if item.file_size > 25_000_000:
                raise ValueError(f'Слишком большая часть XLSX: {item.filename}')
        shared = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            root = ET.fromstring(archive.read('xl/sharedStrings.xml'))
            shared = [''.join(node.text or '' for node in item.findall('.//m:t', _NS))
                      for item in root.findall('m:si', _NS)]
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        relationships = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        targets = {item.get('Id'): item.get('Target') for item in relationships}
        sheet = next((item for item in workbook.findall('.//m:sheet', _NS)
                      if item.get('name') == 'Места'), None)
        if sheet is None:
            raise ValueError('В книге нет листа «Места».')
        relation = sheet.get(f'{{{_NS["r"]}}}id')
        target = targets[relation].lstrip('/')
        sheet_path = target if target.startswith('xl/') else 'xl/' + target
        root = ET.fromstring(archive.read(sheet_path))
        parsed = []
        for row in root.findall('.//m:sheetData/m:row', _NS):
            values = {}
            for cell in row.findall('m:c', _NS):
                match = _CELL_REF.fullmatch(cell.get('r', ''))
                if match:
                    values[match.group(1)] = _cell_value(cell, shared)
            parsed.append(values)
            if len(parsed) > 500:
                raise ValueError('В редакторской книге больше 500 строк.')
    if not parsed:
        raise ValueError('Лист «Места» пуст.')
    headers = {_col_name(index): name for index, name in enumerate(HEADERS, 1)}
    if any(parsed[0].get(column) != name for column, name in headers.items()):
        raise ValueError('Заголовки листа «Места» изменены.')
    return [{name: row.get(column, '') for column, name in headers.items()}
            for row in parsed[1:] if row.get('A')]


def import_xlsx(path, write=False):
    rows = read_xlsx_rows(path)
    corpus = load_corpus()
    glossary = load_glossary()
    known = set(corpus['places'])
    seen = set()
    ready = []
    errors = []
    for number, row in enumerate(rows, 2):
        key = row['ID'].strip()
        if key in seen:
            errors.append(f'строка {number}: повтор ID {key}')
        seen.add(key)
        if key not in known:
            errors.append(f'строка {number}: неизвестный ID {key}')
            continue
        if row['Статус'].strip().casefold() != READY:
            continue
        values = [row[name].strip() for name in HEADERS[6:10]]
        if not all(values):
            errors.append(f'строка {number} ({key}): четыре русских поля обязательны')
            continue
        issue = diagnostics(*values)
        if issue:
            errors.append(f'строка {number} ({key}): {issue}')
            continue
        ready.append((key, values))
    if errors:
        raise ValueError('\n'.join(errors))
    if not ready:
        raise ValueError('Нет строк со статусом «готово».')
    for key, (name, note, about, confidence) in ready:
        glossary['features'][key]['name'] = name
        entry = corpus['places'][key]
        entry.update(name_ru=name, note_ru=note, about_ru=about,
                     confidence_explanation_ru=confidence)
    if write:
        _atomic_json(GLOSSARY_PATH, glossary)
        _atomic_json(CORPUS_PATH, corpus)
    return [key for key, _ in ready]
