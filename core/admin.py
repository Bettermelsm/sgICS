"""Admin 后台：demo 阶段的工作台（配规则、看会话/日志）。"""
from django.contrib import admin
from django.shortcuts import render
from django.urls import path

from .models import (
    ChatMessage,
    ChatSession,
    KeywordRule,
    ReplyLog,
    ReplaceRule,
    ShopAccount,
    TransferRule,
)
from .pipeline import pipeline_for_shop


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = ('direction', 'content', 'source', 'created_at')
    can_delete = False


@admin.register(ShopAccount)
class ShopAccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'platform', 'is_active', 'auto_reply', 'created_at')
    list_editable = ('is_active', 'auto_reply')


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
    list_display = ('customer', 'shop_name', 'source', 'short_incoming',
                    'latency_ms', 'created_at')
    list_filter = ('source', 'session__shop')
    readonly_fields = ('session', 'incoming', 'reply', 'source', 'latency_ms', 'created_at')

    def customer(self, obj):
        return obj.session.customer_name or obj.session.customer_id
    customer.short_description = '客户'

    def shop_name(self, obj):
        return obj.session.shop.name
    shop_name.short_description = '店铺'

    def short_incoming(self, obj):
        return obj.incoming[:30]
    short_incoming.short_description = '客户消息（预览）'
