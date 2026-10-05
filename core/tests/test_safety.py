"""风控模块测试（纯逻辑 + DB 计数）。"""
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone

from core.models import ChatSession, ReplyLog, ShopAccount
from core.safety import (
    SafetyError, check_circuit_breaker, check_rate_limit, check_send_allowed,
    in_service_hours,
)


class SafetyTests(TestCase):
    def setUp(self):
        self.shop = ShopAccount.objects.create(
            name='测试店', platform='douyin', manual_send_enabled=True)
        self.session = ChatSession.objects.create(
            shop=self.shop, customer_id='c1', customer_name='客户A')

    def _sent(self, n):
        for _ in range(n):
            ReplyLog.objects.create(
                session=self.session, incoming='q', reply='a',
                source='keyword:draft', status='sent', sent_at=timezone.now())

    def _failed(self, n):
        for _ in range(n):
            ReplyLog.objects.create(
                session=self.session, incoming='q', reply='a',
                source='keyword:draft', status='failed',
                reviewed_at=timezone.now(), send_error='x')

    def test_flag_off_refused(self):
        self.shop.manual_send_enabled = False
        self.shop.save()
        with self.assertRaises(SafetyError):
            check_send_allowed(self.shop)

    def test_service_hours(self):
        bj = ZoneInfo('Asia/Shanghai')
        self.assertTrue(in_service_hours(datetime(2026, 10, 5, 10, 0, tzinfo=bj)))
        self.assertFalse(in_service_hours(datetime(2026, 10, 5, 2, 0, tzinfo=bj)))

    def test_rate_limit(self):
        with mock.patch('core.safety.SEND_LIMIT_COUNT', 2):
            self._sent(2)
            with self.assertRaises(SafetyError):
                check_rate_limit(self.shop)
        with mock.patch('core.safety.SEND_LIMIT_COUNT', 3):
            check_rate_limit(self.shop)  # 2 < 3 通过

    def test_circuit_breaker(self):
        with mock.patch('core.safety.FAIL_STREAK_LIMIT', 2):
            self._failed(2)
            with self.assertRaises(SafetyError):
                check_circuit_breaker(self.shop)
        with mock.patch('core.safety.FAIL_STREAK_LIMIT', 3):
            check_circuit_breaker(self.shop)  # 2 < 3 通过

    def test_old_failures_not_counted(self):
        with mock.patch('core.safety.FAIL_STREAK_LIMIT', 1):
            with mock.patch('core.safety.FAIL_STREAK_MINUTES', 30):
                old = timezone.now() - timezone.timedelta(hours=2)
                ReplyLog.objects.create(
                    session=self.session, incoming='q', reply='a',
                    source='keyword:draft', status='failed',
                    reviewed_at=old, send_error='x')
                check_circuit_breaker(self.shop)  # 窗口外，不熔断
