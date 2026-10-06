"""草稿审核页测试（发送用 fake 适配器）。"""
from unittest import mock

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import ChatSession, PollerHeartbeat, ReplyLog, ShopAccount


class FakeAdapter:
    last = None

    def __init__(self):
        FakeAdapter.last = self
        self.sent = []

    def login(self):
        return True

    def send_message(self, session_key, content):
        self.sent.append((session_key, content))
        return True

    def transfer_to_human(self, session_key):
        return True

    def close(self):
        pass


class ReviewViewTests(TestCase):
    def setUp(self):
        User.objects.create_superuser('boss', 'b@x.com', 'pw')
        self.shop = ShopAccount.objects.create(
            name='测试店', platform='douyin', manual_send_enabled=True)
        session = ChatSession.objects.create(
            shop=self.shop, customer_id='客户A', customer_name='客户A')
        self.log = ReplyLog.objects.create(
            session=session, incoming='什么时候发货？', reply='48小时内发出',
            source='keyword:draft')
        self.client = Client()
        self.client.force_login(User.objects.get(username='boss'))
        self.url = reverse('admin:core_replylog_review', args=[self.log.id])

    def test_get_renders(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '审核草稿')
        self.assertContains(r, '风控预检')
        self.assertContains(r, '48小时内发出')

    def test_post_send_success(self):
        with mock.patch('core.admin.DouyinAdapter', FakeAdapter):
            with mock.patch('core.safety.in_service_hours', return_value=True):
                r = self.client.post(self.url, {'action': 'send'})
        self.assertEqual(r.status_code, 302)
        self.log.refresh_from_db()
        self.assertEqual(self.log.status, 'sent')
        self.assertEqual(FakeAdapter.last.sent, [('客户A', '48小时内发出')])

    def test_post_send_safety_refused(self):
        self.shop.manual_send_enabled = False
        self.shop.save()
        r = self.client.post(self.url, {'action': 'send'})
        self.assertEqual(r.status_code, 200)  # 留在审核页并显示错误
        self.assertContains(r, '风控拒绝')
        self.log.refresh_from_db()
        self.assertEqual(self.log.status, 'draft')

    def test_post_reject(self):
        r = self.client.post(self.url, {'action': 'reject'})
        self.assertEqual(r.status_code, 302)
        self.log.refresh_from_db()
        self.assertEqual(self.log.status, 'rejected')
        self.assertEqual(self.log.reviewed_by, 'boss')

    def test_anonymous_redirects(self):
        r = Client().get(self.url)
        self.assertEqual(r.status_code, 302)


class HeartbeatCardTests(TestCase):
    def test_heartbeat_status_shown(self):
        from core.context_processors import workbench_guide
        from django.test import RequestFactory
        shop = ShopAccount.objects.create(name='店', platform='douyin')
        PollerHeartbeat.objects.create(
            shop=shop, last_run_at=timezone.now(), last_ok_at=timezone.now())
        cards = workbench_guide(RequestFactory().get('/admin/'))['guide_cards']
        self.assertIn('轮询正常', cards[3]['status'])

    def test_heartbeat_error_shown(self):
        from core.context_processors import workbench_guide
        from django.test import RequestFactory
        shop = ShopAccount.objects.create(name='店', platform='douyin')
        PollerHeartbeat.objects.create(
            shop=shop, last_run_at=timezone.now(), last_error='boom',
            consecutive_failures=2)
        cards = workbench_guide(RequestFactory().get('/admin/'))['guide_cards']
        self.assertIn('轮询异常', cards[3]['status'])


class ReplyLogAdminPermissionTests(TestCase):
    def setUp(self):
        User.objects.create_superuser('boss', 'b@x.com', 'pw')
        self.client = Client()
        self.client.force_login(User.objects.get(username='boss'))

    def test_add_is_forbidden(self):
        # 回复日志只能由消息泵生成：新增页 GET/POST 都应 403
        url = reverse('admin:core_replylog_add')
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {}).status_code, 403)

    def test_changelist_has_no_add_button(self):
        r = self.client.get(reverse('admin:core_replylog_changelist'))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, '增加回复日志')
