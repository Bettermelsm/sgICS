"""消息泵：轮询抖店客服工作台 → 去重入库 → 走回复流水线 → 存草稿。

安全铁律：本命令全程草稿模式，永不调用 adapter.send_message。
真实发送只走 Admin 审核页的人工批准流程（core/sending.py + 风控）。

用法：
    python manage.py poll_douyin --interval 10     # 常驻轮询全部启用店铺
    python manage.py poll_douyin --shop-id 2 --once # 只跑一轮（联调用）
"""
import signal
import time
import traceback

from django.core.management.base import BaseCommand
from django.utils import timezone

from adapters.douyin import DouyinAdapter
from core.models import (
    ChatMessage, ChatSession, PollerHeartbeat, ReplyLog, ShopAccount,
)
from core.pipeline import pipeline_for_shop

# v0.3 安全开关：False = 只存草稿，绝不发送。真实发送走人工审核。
ALLOW_SEND = False

HISTORY_LIMIT = 10
MAX_BACKOFF = 300


class Command(BaseCommand):
    help = '轮询抖店客服新消息并生成回复草稿（常驻服务：只收不发）'

    def add_arguments(self, parser):
        parser.add_argument('--shop-id', type=int, default=None,
                            help='只轮询指定店铺；默认全部启用店铺')
        parser.add_argument('--interval', type=int, default=10, help='轮询间隔秒')
        parser.add_argument('--once', action='store_true', help='只跑一轮就退出')

    def handle(self, *args, **opts):
        if opts['shop_id']:
            shops = list(ShopAccount.objects.filter(
                id=opts['shop_id'], is_active=True))
        else:
            shops = list(ShopAccount.objects.filter(is_active=True))
        if not shops:
            self.stdout.write(self.style.ERROR('没有启用的店铺，先去 Admin 建店。'))
            return
        self._stop = False
        signal.signal(signal.SIGTERM, self._on_signal)
        signal.signal(signal.SIGINT, self._on_signal)

        adapters = {s.id: DouyinAdapter() for s in shops}
        backoff = {s.id: 0 for s in shops}
        self.stdout.write(
            f'消息泵启动：{[s.name for s in shops]}，间隔={opts["interval"]}s，草稿模式')
        try:
            while not self._stop:
                for shop in shops:
                    if self._stop:
                        break
                    try:
                        n = self._pump_once(adapters[shop.id], shop)
                        self._heartbeat(shop, ok=True)
                        backoff[shop.id] = 0
                        self.stdout.write(
                            f'[{time.strftime("%H:%M:%S")}] {shop.name}：本轮 {n} 条新消息')
                    except Exception as e:
                        backoff[shop.id] += 1
                        wait = min(MAX_BACKOFF, 10 * 2 ** backoff[shop.id])
                        self._heartbeat(shop, ok=False, error=str(e)[:300])
                        self.stdout.write(self.style.ERROR(
                            f'{shop.name} 本轮异常（{wait}s 后重试）：{e}'))
                        traceback.print_exc()
                if opts['once']:
                    break
                self._sleep(opts['interval'])
        finally:
            for a in adapters.values():
                a.close()
            self.stdout.write('消息泵已退出。')

    def _on_signal(self, signum, frame):
        self._stop = True

    def _sleep(self, seconds):
        for _ in range(seconds):
            if self._stop:
                break
            time.sleep(1)

    @staticmethod
    def _heartbeat(shop, ok: bool, error: str = ''):
        hb, _ = PollerHeartbeat.objects.get_or_create(shop=shop)
        now = timezone.now()
        hb.last_run_at = now
        if ok:
            hb.last_ok_at = now
            hb.last_error = ''
            hb.consecutive_failures = 0
        else:
            hb.last_error = error
            hb.consecutive_failures += 1
        hb.save()

    def _pump_once(self, adapter, shop) -> int:
        pipeline = pipeline_for_shop(shop, auto_reply=False)  # 强制草稿
        incoming = adapter.poll_new_messages()
        done = 0
        for m in incoming:
            session, _ = ChatSession.objects.get_or_create(
                shop=shop, customer_id=m.session_key,
                defaults={'customer_name': m.customer_name})
            msg, created = ChatMessage.objects.get_or_create(
                session=session, external_id=m.platform_msg_id,
                defaults={'direction': 'in', 'content': m.content})
            if not created:
                continue  # DB 去重：已处理过
            if m.msg_type != 'text':
                continue  # 只处理文本
            history = [
                {'role': 'user' if x.direction == 'in' else 'assistant',
                 'content': x.content}
                for x in session.messages.order_by('-created_at')[:HISTORY_LIMIT][::-1]
            ]
            state = {'is_transferred': session.is_transferred,
                     'ai_fail_count': session.ai_fail_count}
            result = pipeline.handle(m.content, history, state)
            session.is_transferred = state['is_transferred']
            session.ai_fail_count = state['ai_fail_count']
            session.save(update_fields=['is_transferred', 'ai_fail_count'])
            if result.source == 'none':
                continue  # 已转人工，不生成草稿
            # 存草稿：direction=out 但 source 标记 draft，明确"未发送"
            ChatMessage.objects.create(
                session=session, direction='out', content=result.reply,
                source=f'{result.source}:draft')
            ReplyLog.objects.create(
                session=session, incoming=m.content, reply=result.reply,
                source=f'{result.source}:draft', latency_ms=result.latency_ms)
            done += 1
            self.stdout.write(f'  草稿已存：{m.customer_name} ← {result.reply[:40]}')
        assert not ALLOW_SEND, '禁止发送，此断言永不触发仅作保险'
        return done
