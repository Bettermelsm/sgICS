"""抖店适配器测试：
- URL 启发式用 fake 对象（无浏览器）
- Mock 页全流程用真实 Playwright 浏览器（headless）
"""
import tempfile
from pathlib import Path

from django.test import TestCase

from adapters.base import IncomingMessage
from adapters.douyin import DouyinAdapter

MOCK_PAGE = str(Path(__file__).resolve().parent.parent.parent
                / 'adapters' / 'mock_workbench.html')


class FakeLocator:
    def __init__(self, count=0):
        self._count = count

    def count(self):
        return self._count


class FakePage:
    def __init__(self, url='https://fxg.jinritemai.com/'):
        self.url = url

    def locator(self, sel):
        return FakeLocator(count=0)


class LoginHeuristicTests(TestCase):
    def test_rejects_passport_url(self):
        page = FakePage(url='https://passport.jinritemai.com/login')
        self.assertFalse(DouyinAdapter()._is_logged_in(page))

    def test_accepts_plain_url(self):
        page = FakePage(url='https://fxg.jinritemai.com/')
        self.assertTrue(DouyinAdapter()._is_logged_in(page))


class MockBrowserTests(TestCase):
    """真实浏览器 + Mock 工作台：验证两步进入与四个动作。"""

    def _adapter(self):
        tmp = tempfile.mkdtemp()
        return DouyinAdapter(
            storage_state_path=str(Path(tmp) / 'state.json'),
            debug_dir=tmp, mock_path=MOCK_PAGE)

    def test_login_and_poll(self):
        adapter = self._adapter()
        try:
            self.assertTrue(adapter.login())
            msgs = adapter.poll_new_messages()
            self.assertEqual(len(msgs), 2)
            by_name = {m.customer_name: m for m in msgs}
            self.assertIsInstance(msgs[0], IncomingMessage)
            self.assertEqual(by_name['客户A'].content, '请问什么时候发货？')
            self.assertEqual(by_name['客户B'].content, '我要找人工投诉')
            for m in msgs:
                self.assertTrue(m.platform_msg_id.startswith('douyin-'))
            # 第二轮：内存去重
            self.assertEqual(adapter.poll_new_messages(), [])
        finally:
            adapter.close()

    def test_send_and_transfer(self):
        adapter = self._adapter()
        try:
            adapter.login()
            self.assertTrue(adapter.send_message('客户A', '测试回复'))
            self.assertTrue(adapter.transfer_to_human('客户B'))
            log = adapter._page.locator(
                '[data-testid="send-log"]').inner_text()
            self.assertIn('SENT:测试回复', log)
            self.assertIn('TRANSFER', log)
        finally:
            adapter.close()

    def test_message_ids_stable(self):
        # Playwright 同一线程只允许一个 sync 实例：串行验证跨进程 ID 稳定性
        a1 = self._adapter()
        a1.login()
        m1 = a1.poll_new_messages()[0].platform_msg_id
        a1.close()
        a2 = self._adapter()
        try:
            a2.login()
            m2 = a2.poll_new_messages()[0].platform_msg_id
            self.assertEqual(m1, m2)
        finally:
            a2.close()
