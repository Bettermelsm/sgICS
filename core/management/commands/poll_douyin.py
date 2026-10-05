"""消息泵：轮询飞鸽 → 去重入库 → 走回复流水线 → 存草稿。

安全铁律（v0.3）：全程草稿模式，永不调用 adapter.send_message。
即使店铺开了 auto_reply，本命令也只存草稿不发送。
真实发送验证留到 v0.4。

用法：
    python manage.py poll_douyin --shop-id 1 --interval 10   # 持续轮询
    python manage.py poll_douyin --once                     # 只跑一轮（联调用）
"""
import time
import traceback

from django.core.management.base import BaseCommand

from adapters.douyin import DouyinAdapter
from core.llm_gateway import build_gateway
from core.models import (ChatMessage, ChatSession, KeywordRule, ReplyLog,
                         ReplaceRule, ShopAccount, TransferRule)
from core.pipeline import ReplyPipeline, RuleSet

# v0.3 安全开关：False = 只存草稿，绝不发送。v0.4 真实发送验证时再评审打开。
ALLOW_SEND = False

HISTORY_LIMIT = 10


class Command(BaseCommand):
    help = '轮询飞鸽新消息并生成回复草稿（v0.3：只收不发）'

    def add_arguments(self, parser):
        parser.add_argument('--shop-id', type=int, default=1)
        parser.add_argument('--interval', type=int, default=10, help='轮询间隔秒')
        parser.add_argument('--once', action='store_true', help='只跑一轮就退出')

    def handle(self, *args, **opts):
        shop = ShopAccount.objects.get(id=opts['shop_id'])
        if shop.auto_reply:
            self.stdout.write(self.style.WARNING(
                '注意：该店铺 auto_reply=开，但本命令 v0.3 强制草稿模式，不会发送。'))
        adapter = DouyinAdapter()
        self.stdout.write(f'消息泵启动：店铺={shop.name}，间隔={opts["interval"]}s，草稿模式')
        try:
            while True:
                try:
                    n = self._pump_once(adapter, shop)
                    self.stdout.write(f'[{time.strftime("%H:%M:%S")}] 本轮处理 {n} 条新消息')
                except Exception:
                    self.stdout.write(self.style.ERROR('本轮异常（诊断包已生成，继续下一轮）：'))
                    traceback.print_exc()
                if opts['once']:
                    break
                time.sleep(opts['interval'])
        except KeyboardInterrupt:
            self.stdout.write('\n收到中断，退出。')
        finally:
            adapter.close()

    def _pump_once(self, adapter, shop) -> int:
        rules = RuleSet(
            keyword_rules=[(r.keywords, r.reply, r.priority)
                           for r in KeywordRule.objects.filter(shop=shop, is_active=True)],
            transfer_keywords=[r.keywords for r in TransferRule.objects.filter(shop=shop, is_active=True)],
            replace_rules=[(r.pattern, r.replacement)
                           for r in ReplaceRule.objects.filter(shop=shop, is_active=True)],
        )
        pipeline = ReplyPipeline(llm=build_gateway(), rules=rules,
                                 auto_reply=False,  # v0.3 强制草稿
                                 shop_name=shop.name)
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
                continue  # v0.3 只处理文本
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
        assert not ALLOW_SEND, 'v0.3 禁止发送，此断言永不触发仅作保险'
        return done
