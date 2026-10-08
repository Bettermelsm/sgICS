"""抖店客服工作台扫码登录：打开工作台 → 截图二维码 → 用户手机扫码 → 保存登录态。

用法：
    python manage.py login_douyin [--shop-id 1]

登录态按店保存（douyin_state_shop<id>.json，已在 .gitignore），之后免扫码。
后台页面也可用（店铺账号 → 登录管理 → 扫码登录）。
"""
from django.core.management.base import BaseCommand

from adapters.douyin import DouyinAdapter, state_path_for_shop
from core.models import ShopAccount


class Command(BaseCommand):
    help = '抖店客服工作台扫码登录并保存登录态'

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
            return
        adapter = DouyinAdapter(storage_state_path=state_path_for_shop(shop.id))
        try:
            ok = adapter.login()
        finally:
            adapter.close()
        if ok:
            self.stdout.write(self.style.SUCCESS(
                f'登录成功，登录态已保存（{shop.name}）。'))
        else:
            self.stdout.write(self.style.ERROR('登录失败，见上方诊断包。'))
