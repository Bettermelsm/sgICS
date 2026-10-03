"""演示命令：不接真实店铺，模拟客户消息走完整流水线。

用法：
    python manage.py demo_pipeline            # 离线演示（Mock AI）
    python manage.py demo_pipeline --real     # 用 .env 中的 ZHIPU_API_KEY 调真实 GLM

会依次模拟：关键词命中 → 转人工关键词 → 普通咨询(AI兜底) → AI失败转人工，
并打印每一步的决策来源。结果同时写入 DB（admin 里可看）。
"""
from django.core.management.base import BaseCommand

from core.llm_gateway import GLMGateway, MockGateway, build_gateway
from core.models import ChatMessage, ChatSession, KeywordRule, ReplyLog, ShopAccount, TransferRule
from core.pipeline import ReplyPipeline, RuleSet


class Command(BaseCommand):
    help = '模拟客户消息，演示回复流水线'

    def add_arguments(self, parser):
        parser.add_argument('--real', action='store_true', help='使用真实 GLM（需配置 ZHIPU_API_KEY）')

    def handle(self, *args, **options):
        use_real = options['real']
        llm = GLMGateway() if use_real else build_gateway()
        self.stdout.write(f'LLM 网关：{llm.name}')

        shop, _ = ShopAccount.objects.get_or_create(
            name='演示店铺', defaults={'platform': 'douyin', 'auto_reply': False})
        # 预置演示规则（幂等）
        KeywordRule.objects.get_or_create(
            shop=shop, keywords='发货,快递,物流',
            defaults={'reply': '您好，本店默认48小时内发货，物流信息可在订单详情中查看~',
                      'priority': 10})
        TransferRule.objects.get_or_create(shop=shop, keywords='人工,客服,投诉')

        rules = RuleSet(
            keyword_rules=[(r.keywords, r.reply, r.priority)
                           for r in KeywordRule.objects.filter(shop=shop, is_active=True)],
            transfer_keywords=[r.keywords for r in TransferRule.objects.filter(shop=shop, is_active=True)],
            replace_rules=[],
        )
        pipeline = ReplyPipeline(llm=llm, rules=rules, auto_reply=shop.auto_reply,
                                 shop_name=shop.name)

        session, _ = ChatSession.objects.get_or_create(
            shop=shop, customer_id='demo_customer_001',
            defaults={'customer_name': '演示客户'})
        state = {'is_transferred': session.is_transferred,
                 'ai_fail_count': session.ai_fail_count}

        demo_texts = [
            '你好，请问什么时候发货？',   # 关键词命中
            '我要找人工客服投诉',           # 转人工关键词
            '这件衣服掉色吗？',             # AI 兜底（或转人工后不再回复）
        ]
        history = []
        for text in demo_texts:
            result = pipeline.handle(text, history, state)
            history.append({'role': 'user', 'content': text})
            if result.reply:
                history.append({'role': 'assistant', 'content': result.reply})
            self.stdout.write(f'\n客户：{text}')
            self.stdout.write(f'决策来源：{result.source} ｜ 转人工：{result.transferred} ｜ '
                              f'可自动发送：{result.should_send} ｜ 耗时：{result.latency_ms}ms')
            self.stdout.write(f'回复：{result.reply or "（无回复，已转人工）"}')

            ChatMessage.objects.create(session=session, direction='in', content=text)
            if result.reply:
                ChatMessage.objects.create(session=session, direction='out',
                                           content=result.reply, source=result.source)
                ReplyLog.objects.create(session=session, incoming=text,
                                        reply=result.reply, source=result.source,
                                        latency_ms=result.latency_ms)

        session.is_transferred = state['is_transferred']
        session.ai_fail_count = state['ai_fail_count']
        session.save()
        self.stdout.write(self.style.SUCCESS(
            '\n演示完成。去 admin 后台（/admin/）可查看会话、消息与回复日志。'))
