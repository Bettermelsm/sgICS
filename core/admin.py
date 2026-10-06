"""Admin 后台：demo 阶段的工作台（配规则、看会话/日志）。"""
import time

from django.contrib import admin, messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path
from django.utils import timezone
from django.utils.html import format_html

from adapters.douyin import DouyinAdapter

from .kb import guess_doc_type, ingest_doc
from .models import (
    ChatMessage,
    ChatSession,
    KeywordRule,
    KnowledgeChunk,
    KnowledgeDoc,
    ReplyLog,
    ReplaceRule,
    ShopAccount,
    TransferRule,
)
from .pipeline import pipeline_for_shop
from .sending import safety_report, send_draft, transfer_draft
from .safety import SafetyError


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = ('direction', 'content', 'source', 'created_at')
    can_delete = False


@admin.register(ShopAccount)
class ShopAccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'platform', 'is_active', 'auto_reply',
                    'manual_send_enabled', 'created_at')
    list_editable = ('is_active', 'auto_reply', 'manual_send_enabled')


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ('customer_name', 'shop', 'is_transferred', 'ai_fail_count', 'updated_at')
    list_filter = ('shop', 'is_transferred')
    inlines = [ChatMessageInline]


@admin.register(KeywordRule)
class KeywordRuleAdmin(admin.ModelAdmin):
    list_display = ('shop', 'keywords', 'priority', 'is_active')
    list_filter = ('shop', 'is_active')
    change_list_template = 'admin/core/keywordrule/change_list.html'

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('test/', self.admin_site.admin_view(self.test_view),
                 name='core_keywordrule_test'),
        ]
        return custom + urls

    def test_view(self, request):
        """话术测试器：输入一句话，看命中哪条规则 / 转人工 / AI 兜底（只测试不入库）。"""
        shops = ShopAccount.objects.filter(is_active=True)
        shop_id = request.POST.get('shop') or request.GET.get('shop')
        shop = shops.filter(id=shop_id).first() or shops.first()
        text = request.POST.get('text', '').strip() if request.method == 'POST' else ''
        result = None
        if request.method == 'POST' and shop and text:
            pipeline = pipeline_for_shop(shop)
            result = pipeline.handle(text, [], {'is_transferred': False, 'ai_fail_count': 0})
        context = {
            **self.admin_site.each_context(request),
            'title': '话术测试',
            'shops': shops,
            'shop': shop,
            'text': text,
            'result': result,
            'source_labels': {
                'transfer': '转人工', 'keyword': '关键词', 'ai': 'AI 兜底',
                'default': '默认回复', 'none': '不回复',
            },
        }
        return render(request, 'admin/core/rule_test.html', context)


@admin.register(TransferRule)
class TransferRuleAdmin(admin.ModelAdmin):
    list_display = ('shop', 'keywords', 'is_active')
    list_filter = ('shop', 'is_active')


@admin.register(ReplaceRule)
class ReplaceRuleAdmin(admin.ModelAdmin):
    list_display = ('shop', 'pattern', 'replacement', 'is_active')
    list_filter = ('shop', 'is_active')


@admin.register(ReplyLog)
class ReplyLogAdmin(admin.ModelAdmin):
    list_display = ('customer', 'shop_name', 'source', 'status', 'short_incoming',
                    'latency_ms', 'created_at', 'review_link')
    list_filter = ('status', 'source', 'session__shop')
    readonly_fields = ('session', 'incoming', 'reply', 'source', 'latency_ms', 'created_at',
                       'status', 'reviewed_by', 'reviewed_at', 'sent_at', 'send_error')

    def customer(self, obj):
        return obj.session.customer_name or obj.session.customer_id
    customer.short_description = '客户'

    def shop_name(self, obj):
        return obj.session.shop.name
    shop_name.short_description = '店铺'

    def short_incoming(self, obj):
        return obj.incoming[:30]
    short_incoming.short_description = '客户消息（预览）'

    def review_link(self, obj):
        if obj.status != 'draft':
            return '—'
        return format_html('<a href="{}">审核</a>', f'{obj.id}/review/')
    review_link.short_description = '审核'

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('<int:pk>/review/', self.admin_site.admin_view(self.review_view),
                 name='core_replylog_review'),
        ]
        return custom + urls

    def review_view(self, request, pk):
        """草稿审核页：展示风控预检 → 确认发送 / 转人工 / 驳回（二次确认）。"""
        log = get_object_or_404(ReplyLog, pk=pk)
        report = safety_report(log.session.shop)
        if request.method == 'POST' and log.status == 'draft':
            action = request.POST.get('action')
            try:
                if action == 'send':
                    send_draft(log, request.user, DouyinAdapter)
                    messages.success(request, f'草稿 #{log.id} 已发送')
                elif action == 'transfer':
                    transfer_draft(log, request.user, DouyinAdapter)
                    messages.success(request, f'草稿 #{log.id} 已转人工')
                elif action == 'reject':
                    log.status = 'rejected'
                    log.reviewed_by = request.user.username
                    log.reviewed_at = timezone.now()
                    log.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])
                    messages.success(request, f'草稿 #{log.id} 已驳回')
                return redirect('admin:core_replylog_changelist')
            except SafetyError as e:
                messages.error(request, f'风控拒绝：{e}')
            except Exception as e:
                messages.error(request, f'执行失败：{e}')
        context = {
            **self.admin_site.each_context(request),
            'title': f'审核草稿 #{log.id}',
            'log': log,
            'report': report,
        }
        return render(request, 'admin/core/draft_review.html', context)


@admin.register(KnowledgeDoc)
class KnowledgeDocAdmin(admin.ModelAdmin):
    list_display = ('title', 'shop', 'doc_type', 'status', 'chunk_count', 'created_at')
    list_filter = ('shop', 'status')
    readonly_fields = ('status', 'chunk_count', 'error', 'created_at')
    change_list_template = 'admin/core/knowledgedoc/change_list.html'

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('test/', self.admin_site.admin_view(self.test_view),
                 name='core_knowledgedoc_test'),
        ]
        return custom + urls

    def save_model(self, request, obj, form, change):
        if obj.file and not obj.doc_type:
            obj.doc_type = guess_doc_type(obj.file.name)
        super().save_model(request, obj, form, change)
        if not change:
            # 新增文档自动入库（demo 量级同步执行即可）
            try:
                n = ingest_doc(obj)
                self.message_user(request, f'入库成功：{n} 个分块')
            except Exception as e:
                self.message_user(request, f'入库失败：{e}', level=messages.ERROR)

    def test_view(self, request):
        """知识库测试：输入问题，显示检索到的资料块 + AI 回答（不入库）。"""
        shops = ShopAccount.objects.filter(is_active=True)
        shop_id = request.POST.get('shop') or request.GET.get('shop')
        shop = shops.filter(id=shop_id).first() or shops.first()
        question = request.POST.get('q', '').strip() if request.method == 'POST' else ''
        hits, answer, ms, error = [], '', 0, ''
        if request.method == 'POST' and shop and question:
            start = time.time()
            try:
                pipeline = pipeline_for_shop(shop, use_kb=True)
                answer, hits = pipeline.ask_with_kb(question)
            except Exception as e:
                error = str(e)
            ms = int((time.time() - start) * 1000)
        context = {
            **self.admin_site.each_context(request),
            'title': '知识库测试',
            'shops': shops,
            'shop': shop,
            'question': question,
            'hits': hits,
            'answer': answer,
            'ms': ms,
            'error': error,
        }
        return render(request, 'admin/core/kb_test.html', context)


@admin.register(KnowledgeChunk)
class KnowledgeChunkAdmin(admin.ModelAdmin):
    list_display = ('doc', 'ordering', 'short_content')
    list_filter = ('doc__shop', 'doc')
    readonly_fields = ('doc', 'ordering', 'content')

    def short_content(self, obj):
        return obj.content[:60]
    short_content.short_description = '内容预览'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
