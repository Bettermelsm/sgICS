"""人工审核发送测试（fake 适配器，不启动浏览器）。"""
import tempfile
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from core.models import ChatSession, ReplyLog, ShopAccount
from core.safety import SafetyError
from core.sending import safety_report, send_draft, transfer_draft


class FakeAdapter:
    def __init__(self, fail=False):
        self.fail = fail
        self.sent = []
        self.transferred = []
        self.logins = 0
        self.closed = False

    def login(self):
        self.logins += 1
        return True

    def send_message(self, session_key, content):
        if self.fail:
            raise RuntimeError('boom')
        self.sent.append((session_key, content))
        return True

    def send_image(self, session_key, image_path):
        if self.fail:
            raise RuntimeError('boom')
        self.sent.append((session_key, 'IMAGE:' + str(image_path)))
        return True

    def transfer_to_human(self, session_key):
        self.transferred.append(session_key)
        return True

    def close(self):
        self.closed = True


class SendingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('op', 'op@x.com', 'pw')
        self.shop = ShopAccount.objects.create(
            name='测试店', platform='douyin', manual_send_enabled=True)
        self.session = ChatSession.objects.create(
            shop=self.shop, customer_id='客户A', customer_name='客户A')

    def _draft(self, **kw):
        kw.setdefault('source', 'keyword:draft')
        return ReplyLog.objects.create(
            session=self.session, incoming='什么时候发货？',
            reply='48小时内发出', **kw)

    def test_send_success(self):
        log = self._draft()
        fake = FakeAdapter()
        with mock.patch('core.safety.in_service_hours', return_value=True):
            self.assertTrue(send_draft(log, self.user, lambda: fake))
        log.refresh_from_db()
        self.assertEqual(log.status, 'sent')
        self.assertIsNotNone(log.sent_at)
        self.assertEqual(log.reviewed_by, 'op')
        self.assertEqual(fake.sent, [('客户A', '48小时内发出')])
        self.assertTrue(fake.closed)

    def test_send_refused_when_flag_off(self):
        self.shop.manual_send_enabled = False
        self.shop.save()
        log = self._draft()
        created = []
        with self.assertRaises(SafetyError):
            send_draft(log, self.user, lambda: created.append(1) or FakeAdapter())
        self.assertEqual(created, [])  # 风控拒绝时根本不建适配器
        log.refresh_from_db()
        self.assertEqual(log.status, 'draft')

    def test_send_refused_when_not_draft(self):
        log = self._draft(status='sent')
        with self.assertRaises(SafetyError):
            send_draft(log, self.user, FakeAdapter)

    def test_send_failure_recorded(self):
        log = self._draft()
        fake = FakeAdapter(fail=True)
        with mock.patch('core.safety.in_service_hours', return_value=True):
            with self.assertRaises(RuntimeError):
                send_draft(log, self.user, lambda: fake)
        log.refresh_from_db()
        self.assertEqual(log.status, 'failed')
        self.assertIn('boom', log.send_error)

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_send_draft_with_image(self):
        from django.core.files.base import ContentFile
        log = self._draft()
        log.image.save('t.png', ContentFile(b'fakepng'), save=True)
        fake = FakeAdapter()
        with mock.patch('core.safety.in_service_hours', return_value=True):
            self.assertTrue(send_draft(log, self.user, lambda: fake))
        log.refresh_from_db()
        self.assertEqual(log.status, 'sent')
        kinds = [c for _, c in fake.sent]
        self.assertEqual(kinds[0], '48小时内发出')
        self.assertTrue(kinds[1].startswith('IMAGE:'))

    def test_transfer(self):
        log = self._draft(source='transfer:draft')
        fake = FakeAdapter()
        self.assertTrue(transfer_draft(log, self.user, lambda: fake))
        log.refresh_from_db()
        self.assertEqual(log.status, 'transferred')
        self.assertEqual(fake.transferred, ['客户A'])

    def test_safety_report(self):
        report = safety_report(self.shop)
        names = [r[0] for r in report]
        self.assertEqual(names, ['人工发送开关', '服务时间窗口', '频率限制', '熔断检查'])
