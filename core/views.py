"""演示占位页：未开放/未开发的功能统一跳转到这里，避免演示时出现 404 或半成品。

用法：在视图里 `return coming_soon_redirect(request)`，
或模板里链接到 `{% url 'coming_soon' %}`。
"""
from django.shortcuts import redirect, render


def coming_soon(request):
    return render(request, 'coming_soon.html')


def coming_soon_redirect(request):
    """未开放功能统一跳转到占位页。"""
    return redirect('coming_soon')
