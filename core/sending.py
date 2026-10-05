"""人工审核发送：把草稿变成真实动作（发送 / 转人工），全程留审计。

调用方（admin 审核页）负责捕获 SafetyError 并展示。
"""
from django.utils import timezone

from .safety import SafetyError, check_circuit_breaker, check_rate_limit, check_send_allowed, in_service_hours, SERVICE_HOURS


def safety_report(shop):
    """返回 [(检查项, 通过, 说明)]，供审核页展示"为什么不能发"。"""
    report = []
    on = bool(shop.manual_send_enabled)
    report.append(('人工发送开关', on, '已开启' if on else '未开启（去"店铺账号"里打开）'))
    ok = in_service_hours()
    report.append(('服务时间窗口', ok, f'{SERVICE_HOURS}（北京时间）' if ok
                   else f'当前不在 {SERVICE_HOURS}（北京时间）内'))
    for name, fn in (('频率限制', lambda: check_rate_limit(shop)),
                     ('熔断检查', lambda: check_circuit_breaker(shop))):
        try:
            fn()
            report.append((name, True, '通过'))
        except SafetyError as e:
            report.append((name, False, str(e)))
    return report


def _mark(log, user, **fields):
    log.reviewed_by = user.username if user else ''
    log.reviewed_at = timezone.now()
    for k, v in fields.items():
        setattr(log, k, v)
    log.save(update_fields=['reviewed_by', 'reviewed_at', *fields.keys()])


def send_draft(log, user, adapter_factory) -> bool:
    """批准发送一条草稿。成功→sent；失败→failed 并记错。风控不通过抛 SafetyError。"""
    shop = log.session.shop
    if log.status != 'draft':
        raise SafetyError(f'该草稿状态为"{log.get_status_display()}"，不能重复处理')
    check_send_allowed(shop)
    adapter = adapter_factory()
    try:
        adapter.login()
        ok = adapter.send_message(log.session.customer_id, log.reply)
        if ok:
            _mark(log, user, status='sent', sent_at=timezone.now())
        else:
            _mark(log, user, status='failed', send_error='适配器返回 False')
        return ok
    except Exception as e:
        _mark(log, user, status='failed', send_error=str(e)[:500])
        raise
    finally:
        adapter.close()


def transfer_draft(log, user, adapter_factory) -> bool:
    """对转人工草稿执行转人工（只需开人工发送开关，不受时段/频率限制）。"""
    shop = log.session.shop
    if log.status != 'draft':
        raise SafetyError(f'该草稿状态为"{log.get_status_display()}"，不能重复处理')
    if not shop.manual_send_enabled:
        raise SafetyError('该店铺未开启"允许人工审核发送"')
    adapter = adapter_factory()
    try:
        adapter.login()
        ok = adapter.transfer_to_human(log.session.customer_id)
        if ok:
            _mark(log, user, status='transferred')
        else:
            _mark(log, user, status='failed', send_error='适配器返回 False')
        return ok
    except Exception as e:
        _mark(log, user, status='failed', send_error=str(e)[:500])
        raise
    finally:
        adapter.close()
