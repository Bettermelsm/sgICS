"""数据看板测试。"""
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from core.admin import _stats_data
from core.models import ChatMessage, ChatSession, ReplyLog, ShopAccount


class StatsTests(TestCase):
    def setUp(self):
        User.objects.create_superuser('boss', 'b@x.com', 'pw')
        self.shop = ShopAccount.objects.create(name='店', platform='douyin')
        s = ChatSession.objects.create(shop=self.shop, customer_id='c1',
                                       customer_name='A', is_transferred=True)
        ChatSession.objects.create(shop=self.shop, customer_id='c2', customer_name='B')
        ChatMessage.objects.create(session=s, direction='in', content='hi')
        ChatMessage.objects.create(session=s, direction='in', content='hi2')
        ReplyLog.objects.create(session=s, incoming='hi', reply='r',
                                source='keyword:draft', latency_ms=100)
        ReplyLog.objects.create(session=s, incoming='hi2', reply='r2',
                                source='ai:draft', latency_ms=300, status='sent')
        self.client = Client()
        self.client.force_login(User.objects.get(username='boss'))

    def test_stats_data(self):
        d = _stats_data()
        self.assertEqual(d['total_msgs'], 2)
        self.assertEqual(d['transfer_rate'], 50.0)
        self.assertEqual(d['avg_latency'], 200)
        self.assertEqual(d['pending'], 1)
        self.assertEqual(d['sources'], {'keyword': 1, 'ai': 1})
        self.assertEqual(len(d['days']), 7)

    def test_stats_page_renders(self):
        r = self.client.get(reverse('admin:core_replylog_stats'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '数据看板')
        self.assertContains(r, '转人工率')

    def test_stats_anonymous_redirects(self):
        r = Client().get(reverse('admin:core_replylog_stats'))
        self.assertEqual(r.status_code, 302)
