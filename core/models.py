"""客服 demo 数据模型：店铺 / 会话 / 消息 / 三类规则 / 回复日志。"""
from django.db import models


class ShopAccount(models.Model):
    """店铺账号（一个平台的一家店）。"""

    PLATFORM_CHOICES = [
        ('douyin', '抖店/飞鸽'),
    ]

    name = models.CharField('店铺名称', max_length=100)
    platform = models.CharField('平台', max_length=20, choices=PLATFORM_CHOICES, default='douyin')
    is_active = models.BooleanField('启用', default=True)
    # 草稿模式：只生成回复建议，不自动发送。demo/真实店铺测试阶段强烈建议保持开启。
    auto_reply = models.BooleanField('自动回复（关闭=草稿模式）', default=False)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '店铺账号'
        verbose_name_plural = '店铺账号'

    def __str__(self):
        return f'{self.name}（{self.get_platform_display()}）'


class ChatSession(models.Model):
    """一个客户的一次会话。"""

    shop = models.ForeignKey(ShopAccount, verbose_name='店铺', on_delete=models.CASCADE)
    customer_id = models.CharField('客户ID', max_length=100)
    customer_name = models.CharField('客户昵称', max_length=100, blank=True, default='')
    is_transferred = models.BooleanField('已转人工', default=False)
    ai_fail_count = models.IntegerField('AI连续兜底计数', default=0)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '会话'
        verbose_name_plural = '会话'
        unique_together = [('shop', 'customer_id')]

    def __str__(self):
        return f'{self.customer_name or self.customer_id}@{self.shop.name}'


class ChatMessage(models.Model):
    """会话中的单条消息。"""

    DIRECTION_CHOICES = [
        ('in', '客户 → 客服'),
        ('out', '客服 → 客户'),
    ]

    session = models.ForeignKey(ChatSession, verbose_name='会话', on_delete=models.CASCADE, related_name='messages')
    direction = models.CharField('方向', max_length=10, choices=DIRECTION_CHOICES)
    content = models.TextField('内容')
    source = models.CharField('回复来源', max_length=20, blank=True, default='',
                              help_text='keyword / ai / default / human / transfer')
    # 平台原生消息 ID（适配器导入时填写），用于消息去重；NULL 允许多条（如 demo 数据）
    external_id = models.CharField('平台消息ID', max_length=200, null=True, blank=True, default=None)
    created_at = models.DateTimeField('时间', auto_now_add=True)

    class Meta:
        verbose_name = '消息'
        verbose_name_plural = '消息'
        ordering = ['created_at']
        constraints = [
            models.UniqueConstraint(fields=['session', 'external_id'],
                                    name='uniq_session_external_id'),
        ]


class KeywordRule(models.Model):
    """关键词规则：命中则按固定话术回复。"""

    shop = models.ForeignKey(ShopAccount, verbose_name='店铺', on_delete=models.CASCADE)
    keywords = models.CharField('关键词（逗号分隔）', max_length=500, help_text='多个关键词用英文逗号分隔，任一命中即触发')
    reply = models.TextField('回复话术')
    priority = models.IntegerField('优先级（越大越先）', default=0)
    is_active = models.BooleanField('启用', default=True)

    class Meta:
        verbose_name = '关键词规则'
        verbose_name_plural = '关键词规则'
        ordering = ['-priority']


class TransferRule(models.Model):
    """转人工规则：命中则将会话转给人工。"""

    shop = models.ForeignKey(ShopAccount, verbose_name='店铺', on_delete=models.CASCADE)
    keywords = models.CharField('关键词（逗号分隔）', max_length=500)
    is_active = models.BooleanField('启用', default=True)

    class Meta:
        verbose_name = '转人工规则'
        verbose_name_plural = '转人工规则'


class ReplaceRule(models.Model):
    """出站替换规则：对自动回复做文本替换（如品牌名、敏感词）。"""

    shop = models.ForeignKey(ShopAccount, verbose_name='店铺', on_delete=models.CASCADE)
    pattern = models.CharField('被替换文本', max_length=200)
    replacement = models.CharField('替换为', max_length=200)
    is_active = models.BooleanField('启用', default=True)

    class Meta:
        verbose_name = '出站替换规则'
        verbose_name_plural = '出站替换规则'


class ReplyLog(models.Model):
    """每次自动决策的记录：输入、决策来源、结果、耗时。"""

    session = models.ForeignKey(ChatSession, verbose_name='会话', on_delete=models.CASCADE)
    incoming = models.TextField('客户消息')
    reply = models.TextField('系统回复')
    source = models.CharField('决策来源', max_length=20, help_text='transfer / keyword / ai / default')
    latency_ms = models.IntegerField('耗时毫秒', default=0)
    created_at = models.DateTimeField('时间', auto_now_add=True)

    class Meta:
        verbose_name = '回复日志'
        verbose_name_plural = '回复日志'
        ordering = ['-created_at']
