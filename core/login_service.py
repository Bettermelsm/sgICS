"""抖店登录后台服务（v0.9）：扫码/账号/检测都在后台线程跑，前端轮询 LoginJob。

安全：密码只在调用栈里传递、用完即弃，永不入库、永不写日志。
"""
import threading
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import close_old_connections
from django.utils import timezone


def _get_shop(shop_id):
    from core.models import ShopAccount
    return ShopAccount.objects.get(id=shop_id)


def _get_job(job_id):
    from core.models import LoginJob
    return LoginJob.objects.get(id=job_id)


def _finish(job, ok, error=''):
    from core.models import LoginJob
    job.status = 'success' if ok else 'failed'
    job.error = error[:2000]
    job.save(update_fields=['status', 'error', 'updated_at'])
    shop = job.shop
    shop.login_ok = ok
    shop.login_checked_at = timezone.now()
    shop.save(update_fields=['login_ok', 'login_checked_at'])


def _active_job_exists(shop_id) -> bool:
    from core.models import LoginJob
    return LoginJob.objects.filter(
        shop_id=shop_id, status__in=('running', 'waiting_qr')).exists()


def _new_job(shop, method):
    from core.models import LoginJob
    # 清掉该店旧二维码（二维码即登录入口，不留存）
    old = LoginJob.objects.filter(shop=shop).exclude(qr_image='')
    for j in old:
        try:
            Path(j.qr_image.path).unlink(missing_ok=True)
        except Exception:
            pass
    return LoginJob.objects.create(shop=shop, method=method)


def _run_in_thread(target, job_id, *args):
    t = threading.Thread(target=target, args=(job_id, *args), daemon=True)
    t.start()


def start_qr_login(shop):
    """开始扫码登录，返回 LoginJob（前端轮询）。"""
    if _active_job_exists(shop.id):
        raise RuntimeError('该店已有进行中的登录任务，请稍候')
    job = _new_job(shop, 'qr')
    _run_in_thread(_do_qr_login, job.id)
    return job


def _do_qr_login(job_id):
    close_old_connections()
    job = _get_job(job_id)
    try:
        from adapters.douyin import DouyinAdapter, state_path_for_shop

        def on_qr(path):
            j = _get_job(job_id)
            with open(path, 'rb') as f:
                j.qr_image.save(f'qr-{job_id}.png', ContentFile(f.read()), save=False)
            j.status = 'waiting_qr'
            j.save(update_fields=['qr_image', 'status', 'updated_at'])

        adapter = DouyinAdapter(storage_state_path=state_path_for_shop(job.shop_id))
        try:
            adapter.login(on_qr=on_qr)
        finally:
            adapter.close()
        _finish(_get_job(job_id), True)
    except Exception as e:
        _finish(_get_job(job_id), False, str(e))


def start_password_login(shop, username, password):
    """开始账号密码登录，返回 LoginJob。password 仅传给本线程，用完即弃。"""
    if not username or not password:
        raise RuntimeError('账号和密码不能为空')
    if _active_job_exists(shop.id):
        raise RuntimeError('该店已有进行中的登录任务，请稍候')
    job = _new_job(shop, 'password')
    if username != shop.douyin_username:
        shop.douyin_username = username
        shop.save(update_fields=['douyin_username'])
    _run_in_thread(_do_password_login, job.id, username, password)
    return job


def _do_password_login(job_id, username, password):
    close_old_connections()
    try:
        from adapters.douyin import DouyinAdapter, state_path_for_shop
        job = _get_job(job_id)
        adapter = DouyinAdapter(storage_state_path=state_path_for_shop(job.shop_id))
        try:
            adapter.login_with_password(username, password)
        finally:
            adapter.close()
        _finish(_get_job(job_id), True)
    except Exception as e:
        _finish(_get_job(job_id), False, str(e))
    finally:
        password = None  # noqa: F841 — 显式丢弃


def start_check_login(shop):
    """检测登录状态，返回 LoginJob。"""
    if _active_job_exists(shop.id):
        raise RuntimeError('该店已有进行中的登录任务，请稍候')
    job = _new_job(shop, 'check')
    _run_in_thread(_do_check_login, job.id)
    return job


def _do_check_login(job_id):
    close_old_connections()
    try:
        from adapters.douyin import DouyinAdapter, state_path_for_shop
        job = _get_job(job_id)
        adapter = DouyinAdapter(storage_state_path=state_path_for_shop(job.shop_id))
        try:
            ok = adapter.check_login()
        finally:
            adapter.close()
        _finish(_get_job(job_id), ok, '' if ok else '登录态失效，请重新登录')
    except Exception as e:
        _finish(_get_job(job_id), False, str(e))


def logout_shop(shop) -> bool:
    """退出登录：删除该店登录态文件。返回是否删到了文件。"""
    from adapters.douyin import DouyinAdapter, state_path_for_shop
    adapter = DouyinAdapter(storage_state_path=state_path_for_shop(shop.id))
    removed = adapter.logout()
    # 兼容：老版本全局文件也清掉
    from adapters.douyin import DEFAULT_STATE_PATH
    legacy = Path(DEFAULT_STATE_PATH)
    if legacy.exists() and legacy != Path(state_path_for_shop(shop.id)):
        legacy.unlink()
        removed = True
    shop.login_ok = False
    shop.login_checked_at = timezone.now()
    shop.save(update_fields=['login_ok', 'login_checked_at'])
    return removed
