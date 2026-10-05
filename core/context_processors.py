"""模板上下文：把版本号注入所有页面（含 admin 右上角）。"""
from .version import __version__


def version(request):
    return {'cs_version': __version__}
