"""回复流水线单测：验证决策顺序与转人工逻辑。"""
from django.test import SimpleTestCase

from core.llm_gateway import MockGateway
from core.pipeline import ReplyPipeline, RuleSet


def make_pipeline(**kwargs):
    rules = RuleSet(
        keyword_rules=[('发货,快递', '48小时内发货~', 10)],
        transfer_keywords=['人工,投诉'],
        replace_rules=[('本店', 'XX旗舰店')],
    )
    defaults = dict(llm=MockGateway('mock ai reply'), rules=rules,
                    default_reply='默认回复', auto_reply=False, shop_name='演示店铺')
    defaults.update(kwargs)
    return ReplyPipeline(**defaults)


class PipelineTest(SimpleTestCase):
    def test_transfer_keyword_first(self):
        p = make_pipeline()
        state = {}
        r = p.handle('我要找人工投诉', [], state)
        self.assertEqual(r.source, 'transfer')
        self.assertTrue(r.transferred)
        self.assertTrue(state['is_transferred'])

    def test_transferred_session_no_reply(self):
        p = make_pipeline()
        r = p.handle('你好', [], {'is_transferred': True})
        self.assertEqual(r.source, 'none')
        self.assertEqual(r.reply, '')

    def test_keyword_hit(self):
        p = make_pipeline()
        r = p.handle('什么时候发货？', [], {})
        self.assertEqual(r.source, 'keyword')
        self.assertIn('48小时', r.reply)

    def test_ai_fallback(self):
        p = make_pipeline()
        r = p.handle('这件衣服掉色吗', [], {})
        self.assertEqual(r.source, 'ai')
        self.assertIn('mock ai reply', r.reply)

    def test_ai_fail_then_transfer(self):
        class FailGateway(MockGateway):
            def chat(self, messages):
                raise RuntimeError('boom')

        p = make_pipeline(llm=FailGateway(), ai_fail_threshold=2)
        state = {}
        r1 = p.handle('问题1', [], state)
        self.assertEqual(r1.source, 'default')  # 第一次失败走默认回复
        r2 = p.handle('问题2', [], state)
        self.assertEqual(r2.source, 'transfer')  # 达到阈值转人工
        self.assertTrue(r2.transferred)

    def test_replace_rule_applied(self):
        p = make_pipeline()
        # 出站替换作用于默认回复
        p.default_reply = '欢迎光临本店'
        r = p.handle('无意义问题xyz', [], {})
        # '无意义问题xyz' 不命中关键词；MockGateway 正常返回 ai，这里换个思路：
        # 直接测 _apply_replace
        self.assertEqual(p._apply_replace('欢迎光临本店'), '欢迎光临XX旗舰店')

    def test_draft_mode_should_not_send(self):
        p = make_pipeline(auto_reply=False)
        r = p.handle('什么时候发货？', [], {})
        self.assertFalse(r.should_send)
        p2 = make_pipeline(auto_reply=True)
        r2 = p2.handle('什么时候发货？', [], {})
        self.assertTrue(r2.should_send)
