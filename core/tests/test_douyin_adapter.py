"""抖店适配器单测：全部 mock Playwright，不碰真实网络。"""
from django.test import TestCase

from adapters.base import IncomingMessage
from adapters.douyin import DouyinAdapter


class FakeLocator:
    def __init__(self, count=0):
        self._count = count

    def count(self):
        return self._count

    @property
    def first(self):
        return self

    def click(self):
        pass

    def fill(self, text):
        self.filled = text


class FakePage:
    def __init__(self, url='https://fxg.jinritemai.com/', evaluate_result=None):
        self.url = url
        self._eval = evaluate_result or []
        self.goto_urls = []

    def title(self):
        return '飞鸽'

    def goto(self, url, **kwargs):
        self.goto_urls.append(url)

    def wait_for_timeout(self, ms):
        pass

    def locator(self, sel):
        return FakeLocator(count=0)

    def evaluate(self, js, arg):
        return self._eval

    def screenshot(self, path, **kwargs):
        pass

    def content(self):
        return '<html></html>'


class AdapterLoginTests(TestCase):
    def test_is_logged_in_rejects_passport_url(self):
        page = FakePage(url='https://passport.jinritemai.com/login')
        self.assertFalse(DouyinAdapter._is_logged_in(page))

    def test_is_logged_in_accepts_workbench_url(self):
        page = FakePage(url='https://fxg.jinritemai.com/')
        self.assertTrue(DouyinAdapter._is_logged_in(page))

    def test_login_short_circuits_when_state_valid(self):
        adapter = DouyinAdapter(debug_dir='/tmp/cs-test-debug')
        adapter._new_page = lambda: FakePage()  # 已登录态
        # _is_logged_in 对 workbench URL 返回 True，不应抛异常也不应等扫码
        self.assertTrue(adapter.login())


class AdapterPollTests(TestCase):
    def _adapter_with(self, items):
        adapter = DouyinAdapter(debug_dir='/tmp/cs-test-debug')
        page = FakePage(evaluate_result=items)
        adapter._page = page
        adapter._is_logged_in = lambda p: True
        return adapter

    def test_extract_builds_stable_ids(self):
        items = [{'name': '客户A', 'text': '你好，在吗'}]
        adapter = self._adapter_with(items)
        first = adapter.poll_new_messages()
        self.assertEqual(len(first), 1)
        m = first[0]
        self.assertIsInstance(m, IncomingMessage)
        self.assertEqual(m.session_key, '客户A')
        self.assertEqual(m.content, '你好，在吗')
        self.assertTrue(m.platform_msg_id.startswith('douyin-'))
        # 同一内容 ID 稳定（重启后仍能去重）
        adapter2 = self._adapter_with(items)
        self.assertEqual(adapter2.poll_new_messages()[0].platform_msg_id,
                         m.platform_msg_id)

    def test_memory_dedup_within_process(self):
        items = [{'name': '客户A', 'text': '你好'}]
        adapter = self._adapter_with(items)
        self.assertEqual(len(adapter.poll_new_messages()), 1)
        self.assertEqual(adapter.poll_new_messages(), [])  # 第二轮被内存去重

    def test_empty_extract_returns_empty(self):
        adapter = self._adapter_with([])
        self.assertEqual(adapter.poll_new_messages(), [])
