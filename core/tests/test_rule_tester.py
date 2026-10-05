"""话术测试器 admin 视图测试。"""
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from core.models import KeywordRule, ShopAccount, TransferRule


class RuleTestViewTests(TestCase):
    def setUp(self):
        User.objects.create_superuser('boss', 'b@x.com', 'pw')
        self.shop = ShopAccount.objects.create(name='测试店', platform='douyin')
        KeywordRule.objects.create(
            shop=self.shop, keywords='发货,快递', reply='48小时内发出', priority=10)
        TransferRule.objects.create(shop=self.shop, keywords='人工,投诉')
        self.client = Client()
        self.client.force_login(User.objects.get(username='boss'))
        self.url = reverse('admin:core_keywordrule_test')

    def test_get_renders_form(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '话术测试')

    def test_keyword_hit(self):
        r = self.client.post(self.url, {'shop': self.shop.id, 'text': '请问什么时候发货'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'keyword')
        self.assertContains(r, '48小时内发出')
        self.assertContains(r, '命中关键词规则')

    def test_transfer_hit(self):
        r = self.client.post(self.url, {'shop': self.shop.id, 'text': '我要找人工投诉'})
        self.assertContains(r, 'transfer')
        self.assertContains(r, '转接人工客服')

    def test_ai_fallback(self):
        # 测试环境无 API Key → MockGateway 生效
        r = self.client.post(self.url, {'shop': self.shop.id, 'text': '这件衣服会掉色吗'})
        self.assertContains(r, 'ai')

    def test_no_shop_graceful(self):
        ShopAccount.objects.all().delete()
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)

    def test_anonymous_redirects_to_login(self):
        r = Client().get(self.url)
        self.assertEqual(r.status_code, 302)
