"""回复流水线：复刻 ChatGPT-On-CS 的决策顺序。

顺序：转人工判断 → 关键词 → AI 兜底 → 默认回复 → 出站替换。
纯逻辑层，不依赖 Django ORM 之外的任何东西，方便单测。
"""
import time
from dataclasses import dataclass, field

from django.conf import settings

from .llm_gateway import BaseLLMGateway


@dataclass
class PipelineResult:
    reply: str = ''
    source: str = ''  # transfer / keyword / ai / default / none
    transferred: bool = False  # 本轮是否触发了转人工
    should_send: bool = False  # 是否允许自动发送（草稿模式下为 False）
    latency_ms: int = 0
    detail: str = ''  # 命中说明（如"关键词规则：发货（优先级10）"），供测试器展示


@dataclass
class RuleSet:
    """调用方从 DB 装配好的规则集合，pipeline 只读它。"""
    keyword_rules: list = field(default_factory=list)   # [(keywords_str, reply, priority)]
    transfer_keywords: list = field(default_factory=list)  # [keywords_str, ...]
    replace_rules: list = field(default_factory=list)   # [(pattern, replacement)]


def _hit(text: str, keywords_str: str) -> bool:
    text = text.lower()
    return any(k.strip() and k.strip().lower() in text for k in keywords_str.split(','))


class ReplyPipeline:
    """一次客户消息的决策流水线。"""

    def __init__(self, llm: BaseLLMGateway, rules: RuleSet,
                 default_reply: str = '', ai_fail_threshold: int = 3,
                 context_rounds: int = 5, auto_reply: bool = False,
                 shop_name: str = '', retriever=None):
        self.llm = llm
        self.rules = rules
        self.default_reply = default_reply or getattr(settings, 'CS_DEFAULT_REPLY', '')
        self.ai_fail_threshold = ai_fail_threshold or getattr(
            settings, 'CS_AI_FAIL_TRANSFER_THRESHOLD', 3)
        self.context_rounds = context_rounds or getattr(settings, 'CS_CONTEXT_ROUNDS', 5)
        self.auto_reply = auto_reply
        self.shop_name = shop_name
        self.retriever = retriever  # 知识库检索器（v0.7），无则纯 AI 兜底

    def ask_with_kb(self, text: str, history: list = None) -> tuple:
        """知识库问答：检索→拼上下文→LLM 作答。返回 (reply, hits)。"""
        hits = self.retriever.search(text, top_k=3) if self.retriever else []
        kb_context = '\n\n'.join(
            f'【资料{i + 1}】{c.content}' for i, (c, _s) in enumerate(hits))
        messages = self._build_messages(text, history or [], kb_context)
        return self.llm.chat(messages), hits

    def handle(self, text: str, history: list, session_state: dict) -> PipelineResult:
        """history: [{'role': 'user'|'assistant', 'content': str}] 最近 N 轮。
        session_state: {'is_transferred': bool, 'ai_fail_count': int}，调用方负责回写。
        """
        start = time.time()
        result = PipelineResult()

        # 1. 已转人工：不再自动回复
        if session_state.get('is_transferred'):
            result.source = 'none'
            result.latency_ms = self._ms(start)
            return result

        # 2. 转人工关键词
        for kw in self.rules.transfer_keywords:
            if _hit(text, kw):
                session_state['is_transferred'] = True
                result.transferred = True
                result.source = 'transfer'
                result.reply = '已为您转接人工客服，请稍候~'
                result.detail = f'命中转人工关键词：{kw.strip()}'
                result.should_send = self.auto_reply
                result.latency_ms = self._ms(start)
                return result

        # 3. 关键词规则（按优先级）
        for keywords_str, reply, priority in sorted(self.rules.keyword_rules,
                                                    key=lambda r: r[2], reverse=True):
            if _hit(text, keywords_str):
                result.source = 'keyword'
                result.reply = self._apply_replace(reply)
                result.detail = f'命中关键词规则：{keywords_str.strip()}（优先级{priority}）'
                result.should_send = self.auto_reply
                result.latency_ms = self._ms(start)
                return result

        # 4. AI 兜底（先检索知识库）
        try:
            ai_reply, hits = self.ask_with_kb(text, history)
            if ai_reply and ai_reply.strip():
                session_state['ai_fail_count'] = 0
                result.source = 'ai'
                result.reply = self._apply_replace(ai_reply.strip())
                result.detail = f'AI 兜底（{self.llm.name}）' + (
                    f'，引用 {len(hits)} 段资料' if hits else '')
                result.should_send = self.auto_reply
                result.latency_ms = self._ms(start)
                return result
            raise RuntimeError('empty ai reply')
        except Exception:
            session_state['ai_fail_count'] = session_state.get('ai_fail_count', 0) + 1

        # AI 连续失败达到阈值 → 自动转人工
        if session_state['ai_fail_count'] >= self.ai_fail_threshold:
            session_state['is_transferred'] = True
            result.transferred = True
            result.source = 'transfer'
            result.reply = '已为您转接人工客服，请稍候~'
            result.should_send = self.auto_reply
            result.latency_ms = self._ms(start)
            return result

        # 5. 默认回复
        result.source = 'default'
        result.reply = self._apply_replace(self.default_reply)
        result.detail = '默认回复（无规则命中且 AI 不可用）'
        result.should_send = self.auto_reply
        result.latency_ms = self._ms(start)
        return result

    def _build_messages(self, text: str, history: list, kb_context: str = '') -> list:
        system = (
            f'你是「{self.shop_name or "本店"}」的智能客服助手。用简洁、亲切的中文回复客户咨询，'
            '一次只回答当前问题，不要编造订单、价格、库存等事实信息，不确定的请引导客户提供订单号或转人工。'
        )
        if kb_context:
            system += f'\n\n以下是与客户问题相关的内部资料，优先依据它们回答：\n{kb_context}'
        messages = [{'role': 'system', 'content': system}]
        messages.extend(history[-self.context_rounds * 2:])
        messages.append({'role': 'user', 'content': text})
        return messages

    def _apply_replace(self, text: str) -> str:
        for pattern, replacement in self.rules.replace_rules:
            if pattern:
                text = text.replace(pattern, replacement)
        return text

    @staticmethod
    def _ms(start: float) -> int:
        return int((time.time() - start) * 1000)


def ruleset_for_shop(shop) -> RuleSet:
    """从 DB 装配某店铺的规则集合（供命令与 admin 视图共用）。"""
    from .models import KeywordRule, ReplaceRule, TransferRule
    return RuleSet(
        keyword_rules=[(r.keywords, r.reply, r.priority)
                       for r in KeywordRule.objects.filter(shop=shop, is_active=True)],
        transfer_keywords=[r.keywords
                           for r in TransferRule.objects.filter(shop=shop, is_active=True)],
        replace_rules=[(r.pattern, r.replacement)
                       for r in ReplaceRule.objects.filter(shop=shop, is_active=True)],
    )


def pipeline_for_shop(shop, llm=None, auto_reply: bool = False,
                      use_kb: bool = True, embed_fn=None) -> ReplyPipeline:
    """为某店铺装配好流水线（规则来自 DB，LLM 默认按环境自动选择）。

    use_kb=True 且该店有已就绪的知识库文档时，自动接上检索器；
    embed_fn 仅测试用（注入 fake embedding）。
    """
    from .kb import Retriever
    from .llm_gateway import build_gateway
    from .models import KnowledgeDoc
    retriever = None
    if use_kb and KnowledgeDoc.objects.filter(shop=shop, status='ready').exists():
        retriever = Retriever(shop, embed_fn=embed_fn)
    return ReplyPipeline(llm=llm or build_gateway(), rules=ruleset_for_shop(shop),
                         auto_reply=auto_reply, shop_name=shop.name,
                         retriever=retriever)
