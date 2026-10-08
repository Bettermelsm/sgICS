"""v0.9 后台登录管理测试（全部 mock，不启动浏览器）。"""
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from adapters import douyin as douyin_mod
from adapters.douyin import DouyinAdapter, state_path_for_shop
from core import login_service
from core.models import LoginJob, ShopAccount


class StatePathTests(TestCase):
    def test_per_shop_path(self):
        with mock.patch.object(douyin_mod, 'DEFAULT_STATE_PATH',
                               str(Path(tempfile.mkdtemp()) / 'douyin_state.json')):
            p = state_path_for_shop(7)
            self.assertTrue(str(p).endswith('douyin_state_shop7.json'))
            self.assertFalse(p.exists())  # 不存在也不报错，返回分店路径

    def test_legacy_fallback(self):
        d = Path(tempfile.mkdtemp())
        legacy = d / 'douyin_state.json'
        legacy.write_text('{}')
        with mock.patch.object(douyin_mod, 'DEFAULT_STATE_PATH', str(legacy)):
            self.assertEqual(state_path_for_shop(7), legacy)


class LogoutTests(TestCase):
    def test_logout_removes_state(self):
        shop = ShopAccount.objects.create(name='店', platform='douyin',
                                          login_ok=True)
        d = Path(tempfile.mkdtemp())
        sp = d / 'douyin_state_shop1.json'
        sp.write_text('{}')
        with mock.patch.object(douyin_mod, 'DEFAULT_STATE_PATH',
                               str(d / 'douyin_state.json')):
            # shop.id 未必是 1，用实际 id
            real = d / f'douyin_state_shop{shop.id}.json'
            sp.rename(real)
            self.assertTrue(login_service.logout_shop(shop))
            self.assertFalse(real.exists())
        shop.refresh_from_db()
        self.assertFalse(shop.login_ok)
        self.assertIsNotNone(shop.login_checked_at)


class PasswordLoginTests(TestCase):
    def test_no_fields_raises_with_debug_hint(self):
        adapter = DouyinAdapter()
        adapter.check_login = lambda: False
        fake_page = mock.Mock()
        adapter._page = fake_page
        adapter._first_hit = mock.Mock(side_effect=RuntimeError('nope'))
        with self.assertRaises(RuntimeError) as ctx:
            with mock.patch.object(douyin_mod, 'DebugBundle'):
                adapter.login_with_password('u', 'p')
        self.assertIn('nope', str(ctx.exception))


class LoginViewTests(TestCase):
    def setUp(self):
        User.objects.create_superuser('boss', 'b@x.com', 'pw')
        self.shop = ShopAccount.objects.create(name='店', platform='douyin')
        self.client = Client()
        self.client.force_login(User.objects.get(username='boss'))

    def _url(self, name, **kw):
        return reverse(name, args=[self.shop.id] + [kw.get('job_id', 0)]
                       [:1 if 'job_id' not in kw else 2])

    def test_manage_page_renders(self):
        r = self.client.get(
            reverse('admin:core_shopaccount_login', args=[self.shop.id]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '扫码登录')
        self.assertContains(r, '账号密码登录')
        self.assertContains(r, '退出登录')

    def test_start_qr_redirects_to_progress(self):
        job = LoginJob.objects.create(shop=self.shop, method='qr')
        with mock.patch('core.login_service.start_qr_login',
                        return_value=job) as m:
            r = self.client.post(
                reverse('admin:core_shopaccount_login', args=[self.shop.id]),
                {'action': 'start_qr'})
        m.assert_called_once()
        self.assertEqual(
            r.url,
            reverse('admin:core_shopaccount_login_progress',
                    args=[self.shop.id, job.id]))

    def test_logout_action(self):
        with mock.patch('core.login_service.logout_shop',
                        return_value=True) as m:
            r = self.client.post(
                reverse('admin:core_shopaccount_login', args=[self.shop.id]),
                {'action': 'logout'})
        m.assert_called_once()
        self.assertEqual(r.status_code, 302)

    def test_progress_and_status(self):
        job = LoginJob.objects.create(shop=self.shop, method='qr',
                                      status='waiting_qr')
        r = self.client.get(reverse('admin:core_shopaccount_login_progress',
                                    args=[self.shop.id, job.id]))
        self.assertEqual(r.status_code, 200)
        r = self.client.get(reverse('admin:core_shopaccount_login_status',
                                    args=[self.shop.id, job.id]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['status'], 'waiting_qr')

    def test_status_anonymous_denied(self):
        job = LoginJob.objects.create(shop=self.shop, method='qr')
        r = Client().get(reverse('admin:core_shopaccount_login_status',
                                 args=[self.shop.id, job.id]))
        self.assertEqual(r.status_code, 302)
