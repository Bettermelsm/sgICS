"""发送风控：频率限制 / 服务时间窗口 / 熔断。

设计原则：
- 所有计数走 DB（ReplyLog），跨进程有效（web 与 poller 是两个进程）；
- 检查不通过抛 SafetyError，调用方负责展示/记录。
"""
import os
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

SEND_LIMIT_COUNT = int(os.environ.get('SEND_LIMIT_COUNT', '20'))
SEND_LIMIT_MINUTES = int(os.environ.get('SEND_LIMIT_MINUTES', '10'))
SERVICE_HOURS = os.environ.get('SERVICE_HOURS', '9-23')  # Asia/Shanghai
FAIL_STREAK_LIMIT = int(os.environ.get('SEND_FAIL_STREAK_LIMIT', '3'))
FAIL_STREAK_MINUTES = int(os.environ.get('SEND_FAIL_STREAK_MINUTES', '30'))


class SafetyError(Exception):
    """风控拒绝发送。message 可直接展示给审核人。"""


def check_send_allowed(shop) -> None:
    """人工批准发送前的风控检查；不通过抛 SafetyError。"""
    if not shop.manual_send_enabled:
        raise SafetyError('该店铺未开启"允许人工审核发送"（店铺账号里打开）')
    if not in_service_hours():
        raise SafetyError(f'当前不在服务时间窗口内（{SERVICE_HOURS}，北京时间）')
    check_rate_limit(shop)
    check_circuit_breaker(shop)


def in_service_hours(now=None) -> bool:
    start_s, end_s = SERVICE_HOURS.split('-', 1)
    t = (now or timezone.now()).astimezone(ZoneInfo('Asia/Shanghai'))
    return int(start_s) <= t.hour < int(end_s)


def check_rate_limit(shop) -> None:
    from .models import ReplyLog
    since = timezone.now() - timedelta(minutes=SEND_LIMIT_MINUTES)
    n = ReplyLog.objects.filter(
        session__shop=shop, status='sent', sent_at__gte=since).count()
    if n >= SEND_LIMIT_COUNT:
        raise SafetyError(
            f'频率超限：近{SEND_LIMIT_MINUTES}分钟已发送 {n} 条（上限 {SEND_LIMIT_COUNT}）')


def check_circuit_breaker(shop) -> None:
    from .models import ReplyLog
    since = timezone.now() - timedelta(minutes=FAIL_STREAK_MINUTES)
    n = ReplyLog.objects.filter(
        session__shop=shop, status='failed', reviewed_at__gte=since).count()
    if n >= FAIL_STREAK_LIMIT:
        raise SafetyError(
            f'熔断：近{FAIL_STREAK_MINUTES}分钟发送失败 {n} 次，已暂停发送（排查后重试）')
