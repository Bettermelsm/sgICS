"""Admin 右上角版本号单测。"""
from django.contrib.auth.models import User
from django.test import TestCase

from core.version import __version__


class VersionLabelTests(TestCase):
    def test_admin_index_shows_version(self):
        User.objects.create_superuser('admin', 'a@b.com', 'pw')
        self.client.force_login(User.objects.get(username='admin'))
        resp = self.client.get('/admin/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f'v{__version__}')

    def test_login_page_shows_version(self):
        resp = self.client.get('/admin/login/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f'v{__version__}')
