"""Сквозные термины атласа: уровни достоверности, категории, периоды и ссылки
на главы романа. Один источник для страниц, payload карты и печатного атласа.

Канонические данные (Feature.period, Evidence.reference) остаются английскими
и не меняются; здесь только то, как их показывать на EN и RU.
"""
import re

from django.utils.translation import gettext_lazy as _, pgettext_lazy

from .localized_names import _glossary, _is_ru


# ---- Уровни достоверности -------------------------------------------------
# Буква остаётся рядом с названием: «A · Named in the novel».
CONFIDENCE_LABELS = {
    'A': pgettext_lazy('confidence', 'Named in the novel'),
    'B': pgettext_lazy('confidence', 'Inferred'),
    'C': pgettext_lazy('confidence', 'Proposed'),
    'U': pgettext_lazy('confidence', 'No location'),
}
# Строчная форма для мета-строк списка и плиток: «Civic · 1958 · inferred».
CONFIDENCE_META = {
    'A': pgettext_lazy('confidence meta', 'named in the novel'),
    'B': pgettext_lazy('confidence meta', 'inferred'),
    'C': pgettext_lazy('confidence meta', 'proposed'),
    'U': pgettext_lazy('confidence meta', 'no location'),
}
# Одна строка на уровень, везде одинаковая (D10): метод, место, ⓘ, легенда.
CONFIDENCE_EXPLANATIONS = {
    'A': _('The street or the site is named in the text; the exact lot is the atlas’s.'),
    'B': _('Worked out from routes, distances and what stands next to it.'),
    'C': _('The book leaves a gap; the point is the atlas’s proposal.'),
    'U': _('The book doesn’t say where it is; no point on the map.'),
}


def confidence_label(level):
    """«B · Inferred» — подпись уровня с буквой."""
    return f'{level} · {CONFIDENCE_LABELS[level]}'


def confidence_levels():
    """Четыре уровня по порядку — для метода и легенд."""
    return [{'letter': level, 'label': CONFIDENCE_LABELS[level],
             'meta': CONFIDENCE_META[level], 'explanation': CONFIDENCE_EXPLANATIONS[level]}
            for level in 'ABCU']


# ---- Категории ------------------------------------------------------------
# Полная форма — в меню, фильтрах и справочниках; короткая — в мета-строках.
# В EN они совпадают, в RU различаются у Civic и Historical.
KIND_LABELS = {
    'Homes': _('Homes'), 'Civic': _('Civic'), 'Barrens': _('Barrens'),
    'Encounters': _('Encounters'), 'Historical': _('Historical'), 'Outlying': _('Outlying'),
}
KIND_SHORT_LABELS = {
    'Homes': pgettext_lazy('kind short', 'Homes'),
    'Civic': pgettext_lazy('kind short', 'Civic'),
    'Barrens': pgettext_lazy('kind short', 'Barrens'),
    'Encounters': pgettext_lazy('kind short', 'Encounters'),
    'Historical': pgettext_lazy('kind short', 'Historical'),
    'Outlying': pgettext_lazy('kind short', 'Outlying'),
}


def kind_label(kind, short=False):
    return (KIND_SHORT_LABELS if short else KIND_LABELS).get(kind, kind)


# ---- Периоды --------------------------------------------------------------
_YEAR_RANGE = re.compile(r'(?<=\d)-(?=\d)')


def period_label(period, russian=None):
    """Период для показа: в диапазонах лет — короткое тире (1957–58),
    на RU — перевод из proper_names_ru.json (строки из одних чисел не переводятся)."""
    if not period:
        return ''
    if _is_ru(russian):
        period = _glossary().get('periods', {}).get(period, period)
    return _YEAR_RANGE.sub('–', period)


# ---- Главы романа ---------------------------------------------------------
CHAPTER_TITLES = {
    1: 'After the Flood (1957)',
    2: 'After the Festival (1984)',
    3: 'Six Phone Calls (1985)',
    4: 'Ben Hanscom Takes a Fall',
    5: 'Bill Denbrough Beats the Devil',
    6: "One of the Missing: A Tale from the Summer of '58",
    7: 'The Dam in the Barrens',
    8: "Georgie's Room and the House on Neibolt Street",
    9: 'Cleaning Up',
    10: 'The Reunion',
    11: 'Walking Tours',
    12: 'Three Uninvited Guests',
    13: 'The Apocalyptic Rockfight',
    14: 'The Album',
    15: 'The Smoke-Hole',
    16: "Eddie's Bad Break",
    17: 'Another One of the Missing: The Death of Patrick Hockstetter',
    18: 'The Bullseye',
    19: 'In the Watches of the Night',
    20: 'The Circle Closes',
    21: 'Under the City',
    22: 'The Ritual of Chüd',
    23: 'Out',
}
# Ключ интерлюдии — так, как она записана в Evidence.reference.
INTERLUDE_TITLES = {
    'First Interlude': 'Derry: The First Interlude',
    'Second Interlude': 'Derry: The Second Interlude',
    'Third Interlude': 'Derry: The Third Interlude',
    'Fourth Interlude': 'Derry: The Fourth Interlude',
}

# «Ch. 4 - Ben Hanscom Takes a Fall / 4», «Ch. 4», «Ch. 5 - … - I». Название
# в ссылке не используется: его берём из таблицы глав.
_CHAPTER = re.compile(r'Ch\.\s*(\d+)(?:\s*-[^/]*)?(?:\s*/\s*(\d+))?', re.IGNORECASE)
_INTERLUDE = re.compile(r'(First|Second|Third|Fourth)\s+Interlude(?:\s*/\s*(\d+))?',
                        re.IGNORECASE)


def parse_reference(reference):
    """Ссылки на роман в одной строке Evidence.reference.

    Возвращает список кортежей (key, section): key — номер главы (int) или
    ключ интерлюдии ('First Interlude'), section — номер раздела или ''.
    Позиции в тексте вида ``[1598, 1775]`` ссылками на главы не считаются.
    """
    refs = []
    for part in reference.split(';'):
        part = ' '.join(part.split())
        if match := _CHAPTER.fullmatch(part):
            number = int(match[1])
            if number in CHAPTER_TITLES:
                refs.append((number, match[2] or ''))
        elif match := _INTERLUDE.fullmatch(part):
            refs.append((match[1].capitalize() + ' Interlude', match[2] or ''))
    return refs


def chapter_title(key, russian=None):
    english = CHAPTER_TITLES[key] if isinstance(key, int) else INTERLUDE_TITLES[key]
    if _is_ru(russian):
        return _glossary().get('chapters', {}).get(str(key), english)
    return english


def chapter_label(key, section='', russian=None):
    """«Ch. 4 · Ben Hanscom Takes a Fall · §4» / «Гл. 4 · Бен Хэнском падает · §4».
    У интерлюдии номера главы нет: «Derry: The First Interlude · §2»."""
    parts = []
    if isinstance(key, int):
        parts.append(('Гл. ' if _is_ru(russian) else 'Ch. ') + str(key))
    parts.append(chapter_title(key, russian))
    if section:
        parts.append('§' + section)
    return ' · '.join(parts)


def novel_references(references, russian=None):
    """Подписи «In the novel» для набора Evidence.reference: без повторов,
    в порядке записей, позиции в тексте отброшены."""
    labels = []
    for reference in references:
        for key, section in parse_reference(reference):
            label = chapter_label(key, section, russian)
            if label not in labels:
                labels.append(label)
    return labels
