"""config URL Configuration."""
from django.contrib import admin
from django.urls import path

from core import views as core_views

urlpatterns = [
    path('admin/', admin.site.urls),
    # 演示占位页：未开放功能统一跳转到这里
    path('coming-soon/', core_views.coming_soon, name='coming_soon'),
]
