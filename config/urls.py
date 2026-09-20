from django.conf.urls.i18n import i18n_patterns
from django.urls import path
from django.views.i18n import JavaScriptCatalog
from atlas import views

# Служебные маршруты живут без языкового префикса; страницы — в двух версиях,
# английская (по умолчанию) без префикса, русская под /ru/.
urlpatterns = [path('api/v1/map/', views.map_data, name='map_data'),
               path('api/v1/photos/', views.photo_data, name='photo_data'),
               path('media/<path:media_path>', views.media, name='media'),
               path('sitemap.xml', views.sitemap, name='sitemap'),
               path('robots.txt', views.robots, name='robots'),
               path('healthz/', views.health, name='health')]
urlpatterns += i18n_patterns(
    path('', views.index, name='index'), path('photos/', views.gallery, name='gallery'),
    path('photos/<int:photo_id>/', views.photo_page, name='photo'),
    path('places/<slug:slug>/', views.place_page, name='place'),
    path('method/', views.method, name='method'),
    path('jsi18n/', JavaScriptCatalog.as_view(), name='javascript-catalog'),
    prefix_default_language=False)
