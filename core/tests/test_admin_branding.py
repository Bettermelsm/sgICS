"""Admin 品牌测试：左上角 sgICS + 查看站点指向工作台。"""
from django.contrib.auth.models import User
from django.test import Client, TestCase


class AdminBrandingTests(TestCase):
    def setUp(self):
        User.objects.create_superuser('boss', 'b@x.com', 'pw')
        self.client = Client()
        self.client.force_login(User.objects.get(username='boss'))

    def test_site_header_is_sgics(self):
        r = self.client.get('/admin/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'sgICS')
        self.assertNotContains(r, 'Django 管理')

    def test_view_site_points_to_workbench(self):
        # "查看站点" 不再 404：指向工作台首页
        r = self.client.get('/admin/')
        self.assertContains(r, 'href="/admin/"')
