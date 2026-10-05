"""抖店客服工作台扫码登录：打开工作台 → 截图二维码 → 用户手机扫码 → 保存登录态。

用法：
    python manage.py login_douyin

登录态保存在 douyin_state.json（已在 .gitignore），之后免扫码。
"""
from django.core.management.base import BaseCommand

from adapters.douyin import DouyinAdapter, QR_SCREENSHOT


class Command(BaseCommand):
    help = '抖店客服工作台扫码登录并保存登录态'

    def handle(self, *args, **opts):
        adapter = DouyinAdapter()
        try:
            ok = adapter.login()
        finally:
            adapter.close()
        if ok:
            self.stdout.write(self.style.SUCCESS('登录成功，登录态已保存。'))
        else:
            self.stdout.write(self.style.ERROR('登录失败，见上方诊断包。'))
