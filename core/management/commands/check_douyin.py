"""登录态检查：轻量判断工作台登录是否有效，不触发扫码流程。

用法：
    python manage.py check_douyin
退出码 0=有效，1=失效（此时跑 login_douyin 重新扫码）。
"""
from django.core.management.base import BaseCommand

from adapters.douyin import DouyinAdapter


class Command(BaseCommand):
    help = '检查抖店工作台登录态是否有效'

    def handle(self, *args, **opts):
        adapter = DouyinAdapter()
        try:
            if adapter.check_login():
                self.stdout.write(self.style.SUCCESS('登录态有效'))
            else:
                self.stdout.write(self.style.ERROR(
                    '登录态失效：请跑 python manage.py login_douyin 重新扫码'))
                raise SystemExit(1)
        finally:
            adapter.close()
