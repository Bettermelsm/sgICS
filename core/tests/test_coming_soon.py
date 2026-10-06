"""演示占位页测试。"""
from django.test import RequestFactory, TestCase
from django.urls import reverse

from core.views import coming_soon_redirect


class ComingSoonTests(TestCase):
    def test_page_renders(self):
        r = self.client.get(reverse('coming_soon'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '当前功能模块尚未开放，请联系开发团队授权')
        self.assertContains(r, 'junjun.webp')

    def test_redirect_helper(self):
        resp = coming_soon_redirect(RequestFactory().get('/x/'))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('coming_soon'))
