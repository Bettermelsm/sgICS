"""Admin 后台：demo 阶段的工作台（配规则、看会话/日志）。"""
from django.contrib import admin

from .models import (
    ChatMessage,
    ChatSession,
    KeywordRule,
    ReplyLog,
    ReplaceRule,
    ShopAccount,
    TransferRule,
)


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
