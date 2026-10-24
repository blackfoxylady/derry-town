"""JSON-LD (schema.org) для поисковиков.

Словари собираются из тех же объектов и переводов, что уходят в шаблоны,
поэтому разметка всегда повторяет видимое содержимое страницы. Город
вымышленный и реальных координат нет, поэтому типы Place/GeoCoordinates
не используются: страницы мест размечены как статьи о романе
(Article + about → Book), фотографии — как ImageObject.
"""
from django.urls import reverse
from django.utils.translation import get_language, gettext as _

from .terms import period_label


def _root(request):
    return request.build_absolute_uri('/')


def _breadcrumb_root_name():
    """Корень крошек — карта (как в видимых крошках, breadcrumbs.html)."""
    return _('Map')


def _graph(request, *nodes):
    """Общая обёртка: WebSite и роман-первоисточник есть на каждой странице,
    узлы страницы ссылаются на них по @id."""
    root = _root(request)
    website = {'@type': 'WebSite', '@id': root + '#website', 'url': root,
               'name': 'Derry', 'inLanguage': ['en', 'ru'],
               'about': {'@id': root + '#book'}}
    book = {'@type': 'Book', '@id': root + '#book', 'name': 'It',
            'author': {'@type': 'Person', 'name': 'Stephen King'},
            'datePublished': '1986',
            'sameAs': 'https://en.wikipedia.org/wiki/It_(novel)'}
    return {'@context': 'https://schema.org', '@graph': [website, book, *nodes]}


def _page(request, page_type, name, description=''):
    node = {'@type': page_type, 'url': request.build_absolute_uri(request.path),
            'name': str(name), 'inLanguage': get_language() or 'en',
            'isPartOf': {'@id': _root(request) + '#website'},
            'about': {'@id': _root(request) + '#book'}}
    if description:
        node['description'] = str(description)
    return node


def _breadcrumbs(request, *items):
    """items — пары (название, путь); у текущей страницы путь пустой."""
    elements = []
    for position, (name, path) in enumerate(items, 1):
        element = {'@type': 'ListItem', 'position': position, 'name': name}
        if path:
            element['item'] = request.build_absolute_uri(path)
        elements.append(element)
    return {'@type': 'BreadcrumbList', 'itemListElement': elements}


def index(request, name, description):
    return _graph(request, _page(request, 'Map', name, description))


def gallery(request, name, description, current=''):
    crumbs = [(_breadcrumb_root_name(), reverse('index'))]
    if current:
        crumbs += [(_('Photographs'), reverse('gallery')), (current, '')]
    else:
        crumbs.append((_('Photographs'), ''))
    return _graph(request, _page(request, ['CollectionPage', 'ImageGallery'], name, description),
                  _breadcrumbs(request, *crumbs))


def places(request, name, description, cards):
    collection = _page(request, 'CollectionPage', name, description)
    collection['mainEntity'] = {'@id': request.build_absolute_uri(request.path) + '#places'}
    item_list = {
        '@type': 'ItemList', '@id': request.build_absolute_uri(request.path) + '#places',
        'numberOfItems': len(cards),
        'itemListElement': [
            {'@type': 'ListItem', 'position': position,
             'name': card['name'],
             'url': request.build_absolute_uri(card['url'])}
            for position, card in enumerate(cards, 1)
        ],
    }
    return _graph(request, collection, item_list,
                  _breadcrumbs(request, (_breadcrumb_root_name(), reverse('index')),
                               (_('Places'), '')))


def method(request, name, description, breadcrumb):
    """Sources & method: WebPage и крошки Map › Sources & method."""
    return _graph(request, _page(request, 'WebPage', name, description),
                  _breadcrumbs(request, (_breadcrumb_root_name(), reverse('index')),
                               (str(breadcrumb), '')))


def editorial(request, name, description, breadcrumb, published, in_articles=False):
    """Long-form, source-backed guide page. Статьи лежат в разделе Articles
    (Map / Articles / заголовок), страница печатной карты — сразу под картой."""
    article = _page(request, 'Article', name, description)
    article['headline'] = str(name)
    article['author'] = {'@type': 'Organization', 'name': 'Derry', 'url': _root(request)}
    article['publisher'] = {'@type': 'Organization', 'name': 'Derry', 'url': _root(request)}
    article['datePublished'] = published.isoformat()
    article['dateModified'] = published.isoformat()
    crumbs = [(_breadcrumb_root_name(), reverse('index'))]
    if in_articles:
        crumbs.append((_('Articles'), reverse('articles')))
    crumbs.append((breadcrumb, ''))
    return _graph(request, article, _breadcrumbs(request, *crumbs))


def articles(request, name, description, items):
    """/articles/: CollectionPage со списком статей (ItemList) и крошками Map › Articles."""
    url = request.build_absolute_uri(request.path)
    collection = _page(request, 'CollectionPage', name, description)
    collection['mainEntity'] = {'@id': url + '#articles'}
    item_list = {
        '@type': 'ItemList', '@id': url + '#articles', 'numberOfItems': len(items),
        'itemListElement': [
            {'@type': 'ListItem', 'position': position, 'name': item['heading'],
             'url': request.build_absolute_uri(item['url'])}
            for position, item in enumerate(items, 1)
        ],
    }
    return _graph(request, collection, item_list,
                  _breadcrumbs(request, (_breadcrumb_root_name(), reverse('index')),
                               (_('Articles'), '')))


def place(request, ctx):
    """Страница места из готового context'а place_page."""
    feature, note = ctx['feature'], ctx['note']
    name = ctx['feature_name']
    period = period_label(feature.period)
    page = _page(request, 'Article', name, note or (name + (' · ' + period if period else '')))
    page['headline'] = name
    if period:
        page['temporalCoverage'] = period
    if ctx['og_photo']:
        page['image'] = request.build_absolute_uri(ctx['og_photo'])
    return _graph(request, page,
                  _breadcrumbs(request, (_breadcrumb_root_name(), reverse('index')),
                               (_('Places'), reverse('places')), (name, '')))


def photo(request, ctx):
    """Страница фотографии из готового context'а photo_page: главный узел —
    ImageObject, по которому Google Images показывает атрибуцию."""
    p, caption = ctx['photo'], ctx['caption']
    name = caption or ctx['alt']
    root = _root(request)
    image = {'@type': 'ImageObject', 'name': name,
             'url': request.build_absolute_uri(request.path),
             'contentUrl': request.build_absolute_uri(ctx['urls']['original']),
             'thumbnailUrl': request.build_absolute_uri(ctx['urls']['thumb']),
             'width': p.width, 'height': p.height,
             'representativeOfPage': True,
             'inLanguage': get_language() or 'en',
             'isPartOf': {'@id': root + '#website'},
             'creator': {'@type': 'Organization', 'name': 'Derry', 'url': root},
             'creditText': 'Derry'}
    if caption:
        image['caption'] = caption
    if p.year:
        image['temporalCoverage'] = str(p.year)
    keywords = [c['name'] for c in ctx['characters']] + [t['name'] for t in ctx['tags']]
    if keywords:
        image['keywords'] = ', '.join(keywords)
    crumbs = _breadcrumbs(request, (_breadcrumb_root_name(), reverse('index')),
                          (_('Photographs'), reverse('gallery')), (ctx.get('breadcrumb') or name, ''))
    return _graph(request, image, crumbs)
