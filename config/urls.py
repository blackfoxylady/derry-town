from django.urls import path
from atlas import views

urlpatterns = [path('', views.index), path('photos/', views.gallery),
               path('photos/<int:photo_id>/', views.photo_page), path('api/v1/map/', views.map_data),
               path('api/v1/photos/', views.photo_data),
               path('media/<path:media_path>', views.media), path('healthz/', views.health)]
