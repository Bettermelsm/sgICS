"""模板上下文：版本号 + Admin 首页引导卡片。"""
import os
from pathlib import Path

from django.urls import reverse
from django.utils import timezone

from .version import __version__


def version(request):
    return {'cs_version': __version__}


def workbench_guide(request):
    """Admin 首页引导卡片数据（编号步骤 + 一句话做法 + 实时状态）。"""
    if not request.path.startswith('/admin'):
        return {}
    from .models import KeywordRule, ReplyLog, ShopAccount, TransferRule

    shop_n = ShopAccount.objects.count()
    kw_n = KeywordRule.objects.filter(is_active=True).count()
    tr_n = TransferRule.objects.filter(is_active=True).count()
    state_ok = Path(os.environ.get('DOUYIN_STATE_PATH', 'douyin_state.json')).exists()
    today_drafts = ReplyLog.objects.filter(
        created_at__date=timezone.now().date()).count()

    cards = [
        {
            'num': '01', 'title': '建店铺', 'done': shop_n > 0,
            'desc': '在「店铺账号」添加你的真实店；「自动回复」保持关闭＝草稿模式，只存草稿不发送。',
            'status': f'已建 {shop_n} 家店铺' if shop_n else '还没建店，先走这一步',
            'url': reverse('admin:core_shopaccount_changelist'), 'action': '去建店',
        },
        {
            'num': '02', 'title': '配话术', 'done': kw_n + tr_n > 0,
            'desc': '「关键词规则」命中即按话术回；「转人工规则」命中即转人工。优先级数字越大越先。',
            'status': f'关键词 {kw_n} 条 · 转人工 {tr_n} 条' if kw_n + tr_n else '还没配规则',
            'url': reverse('admin:core_keywordrule_changelist'), 'action': '去配话术',
        },
        {
            'num': '03', 'title': '接飞鸽', 'done': state_ok,
            'desc': 'WSL 里跑 python manage.py login_douyin，手机扫码登录飞鸽工作台（详见 docs/DOUYIN.md）。',
            'status': '登录态已保存' if state_ok else '未登录，扫码后这里会变绿',
            'url': None, 'action': '跑 login_douyin 命令',
        },
        {
            'num': '04', 'title': '收草稿', 'done': today_drafts > 0,
            'desc': '跑 python manage.py poll_douyin 收消息 → 走流水线 → 只存草稿；去「回复日志」审阅，人工决定发不发。',
            'status': f'今日已存草稿 {today_drafts} 条' if today_drafts else '还没跑过消息泵',
            'url': reverse('admin:core_replylog_changelist'), 'action': '看回复日志',
        },
    ]
    return {'guide_cards': cards}
