"""登录态检查：轻量判断工作台登录是否有效，不触发扫码流程。

用法：
    python manage.py check_douyin [--shop-id 1]
退出码 0=有效，1=失效（此时跑 login_douyin 重新扫码，或去后台登录管理页）。
"""
from django.core.management.base import BaseCommand

from adapters.douyin import DouyinAdapter, state_path_for_shop
from core.models import ShopAccount


class Command(BaseCommand):
    help = '检查抖店工作台登录态是否有效'

    def add_arguments(self, parser):
        parser.add_argument('--shop-id', type=int, default=0,
                            help='店铺 ID（默认第一家启用的店）')

    def handle(self, *args, **opts):
        if opts['shop_id']:
            shop = ShopAccount.objects.filter(
                id=opts['shop_id'], is_active=True).first()
        else:
            shop = ShopAccount.objects.filter(is_active=True).first()
        if not shop:
            self.stdout.write(self.style.ERROR('没有启用的店铺，先去 Admin 建店。'))
            raise SystemExit(1)
        adapter = DouyinAdapter(storage_state_path=state_path_for_shop(shop.id))
        try:
            if adapter.check_login():
                self.stdout.write(self.style.SUCCESS(f'登录态有效（{shop.name}）'))
            else:
                self.stdout.write(self.style.ERROR(
                    f'登录态失效（{shop.name}）：请跑 login_douyin 重新扫码，'
                    '或去后台「店铺账号 → 登录管理」'))
                raise SystemExit(1)
        finally:
            adapter.close()
