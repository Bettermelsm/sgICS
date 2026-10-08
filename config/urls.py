"""config URL Configuration."""
from django.conf import settings
from django.contrib import admin
from django.urls import path

from core import views as core_views

# sgICS 品牌：左上角 "Django 管理" 改为产品名；
# "查看站点" 指向工作台首页（本项目暂无对外前台，/ 原来是 404）
admin.site.site_header = 'sgICS'
admin.site.site_title = 'sgICS'
admin.site.site_url = '/admin/'

urlpatterns = [
    path('admin/', admin.site.urls),
    # 演示占位页：未开放功能统一跳转到这里
    path('coming-soon/', core_views.coming_soon, name='coming_soon'),
]

# v0.9：开发/演示环境由 Django 直接提供上传文件访问（二维码、配图等）
if settings.DEBUG:
    from django.conf.urls.static import static
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
