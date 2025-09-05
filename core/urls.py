from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('book/', views.book, name='book'),
    path('confirm/<str:code>/', views.confirm, name='confirm'),
    path('appointments/', views.appointments, name='appointments'),
    path('cancel/<str:code>/', views.cancel, name='cancel'),
    path('cancel-lookup/', views.cancel_lookup, name='cancel_lookup'),
    path('api/cancel-check/', views.cancel_check, name='cancel_check'),
]
