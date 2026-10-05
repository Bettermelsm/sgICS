"""消息泵单测：去重 / 草稿存储 / 永不发送。"""
from django.core.management import call_command
from django.test import TestCase

from adapters.base import IncomingMessage
from core.management.commands.poll_douyin import ALLOW_SEND, Command
from core.models import (ChatMessage, ChatSession, KeywordRule, ReplyLog,
                         ShopAccount, TransferRule)


class FakeAdapter:
    def __init__(self, messages):
        self._messages = messages
        self.sent = []

    def poll_new_messages(self):
        return self._messages

    def send_message(self, session_key, content):
        self.sent.append((session_key, content))
        return True

    def close(self):
        pass


def make_incoming(mid, name='客户A', text='你好', msg_type='text'):
    return IncomingMessage(platform_msg_id=mid, session_key='cust_001',
                           customer_name=name, content=text, msg_type=msg_type)


class PumpTests(TestCase):
    def setUp(self):
        self.shop = ShopAccount.objects.create(name='测试店', platform='douyin')
        KeywordRule.objects.create(shop=self.shop, keywords='发货',
                                   reply='48小时内发货', priority=10)
        TransferRule.objects.create(shop=self.shop, keywords='人工')
        self.cmd = Command()

    def test_new_message_creates_draft_not_sent(self):
        adapter = FakeAdapter([make_incoming('m1', text='请问什么时候发货？')])
        n = self.cmd._pump_once(adapter, self.shop)
        self.assertEqual(n, 1)
        session = ChatSession.objects.get(shop=self.shop, customer_id='cust_001')
        inbound = ChatMessage.objects.get(session=session, external_id='m1')
        self.assertEqual(inbound.direction, 'in')
        draft = ChatMessage.objects.get(session=session, direction='out')
        self.assertEqual(draft.content, '48小时内发货')
        self.assertTrue(draft.source.endswith(':draft'))
        self.assertEqual(ReplyLog.objects.count(), 1)
        self.assertEqual(adapter.sent, [])  # 绝不发送

    def test_db_dedup_same_external_id(self):
        adapter = FakeAdapter([make_incoming('m1', text='你好')])
        self.cmd._pump_once(adapter, self.shop)
        # 模拟重启：新 adapter（内存去重已清空），同样消息再来一轮
        adapter2 = FakeAdapter([make_incoming('m1', text='你好')])
        n = self.cmd._pump_once(adapter2, self.shop)
        self.assertEqual(n, 0)
        session = ChatSession.objects.get(shop=self.shop, customer_id='cust_001')
        self.assertEqual(
            ChatMessage.objects.filter(session=session, direction='in').count(), 1)

    def test_non_text_skipped(self):
        adapter = FakeAdapter([make_incoming('m2', msg_type='image', text='[图片]')])
        n = self.cmd._pump_once(adapter, self.shop)
        self.assertEqual(n, 0)
        # 消息入库了（已读标记），但不生成草稿
        session = ChatSession.objects.get(shop=self.shop, customer_id='cust_001')
        self.assertEqual(ChatMessage.objects.filter(session=session).count(), 1)
        self.assertEqual(ReplyLog.objects.count(), 0)

    def test_transfer_stores_draft_and_marks_session(self):
        adapter = FakeAdapter([make_incoming('m3', text='我要找人工投诉')])
        n = self.cmd._pump_once(adapter, self.shop)
        self.assertEqual(n, 1)
        session = ChatSession.objects.get(shop=self.shop, customer_id='cust_001')
        self.assertTrue(session.is_transferred)
        draft = ChatMessage.objects.get(session=session, direction='out')
        self.assertEqual(draft.source, 'transfer:draft')
        # 转人工后再次来消息：不再生成草稿
        adapter2 = FakeAdapter([make_incoming('m4', text='还在吗')])
        self.assertEqual(self.cmd._pump_once(adapter2, self.shop), 0)

    def test_allow_send_hard_off(self):
        self.assertFalse(ALLOW_SEND)
