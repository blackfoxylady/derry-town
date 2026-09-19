from django.urls import path
from atlas import views

urlpatterns = [path('', views.index), path('api/v1/map/', views.map_data),
               path('healthz/', views.health)]
