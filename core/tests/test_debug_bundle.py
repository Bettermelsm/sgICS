"""诊断包单测：异常时自动收集截图/DOM/日志。"""
import shutil
import tempfile
from pathlib import Path

from django.test import TestCase

from adapters.debug import DebugBundle


class FakePage:
    def __init__(self, fail_screenshot=False):
        self.url = 'https://fxg.jinritemai.com/'
        self._fail_shot = fail_screenshot

    def title(self):
        return '飞鸽工作台'

    def screenshot(self, path, full_page=False):
        if self._fail_shot:
            raise RuntimeError('截图炸了')
        Path(path).write_text('fake-png')

    def content(self):
        return '<html><body>fake dom</body></html>'


class DebugBundleTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_bundle_created_on_exception(self):
        page = FakePage()
        with self.assertRaises(ValueError):
            with DebugBundle(page, name='login', out_dir=self.tmp) as dbg:
                dbg.note('做到一半')
                raise ValueError('boom')
        bundles = list(Path(self.tmp).glob('login-*'))
        self.assertEqual(len(bundles), 1)
        b = bundles[0]
        self.assertTrue((b / 'screenshot.png').exists())
        dom = (b / 'dom.html').read_text(encoding='utf-8')
        self.assertIn('fake dom', dom)
        info = (b / 'info.txt').read_text(encoding='utf-8')
        self.assertIn('boom', info)
        self.assertIn('做到一半', info)
        self.assertIn('fxg.jinritemai.com', info)

    def test_no_bundle_when_clean(self):
        page = FakePage()
        with DebugBundle(page, name='poll', out_dir=self.tmp):
            pass
        self.assertEqual(list(Path(self.tmp).glob('poll-*')), [])

    def test_screenshot_failure_does_not_mask_original_error(self):
        page = FakePage(fail_screenshot=True)
        with self.assertRaises(KeyError):
            with DebugBundle(page, name='x', out_dir=self.tmp):
                raise KeyError('original')
        b = list(Path(self.tmp).glob('x-*'))[0]
        info = (b / 'info.txt').read_text(encoding='utf-8')
        self.assertIn('original', info)
        self.assertIn('截图失败', info)
