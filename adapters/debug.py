"""诊断包：一键收集失败现场，供远程排错。

用法：
    with DebugBundle(page, name='login') as dbg:
        ...  # 出异常时自动截图 + 存 DOM + 写日志
        dbg.note('已到达会话列表')

产出目录 debug/<name>-<时间戳>/：
    - screenshot.png  页面截图
    - dom.html        页面 HTML（用于校准 selector）
    - info.txt        URL、标题、异常堆栈、note 日志
把整个目录发给开发者即可定位问题。
"""
import time
import traceback
from pathlib import Path


class DebugBundle:
    def __init__(self, page, name: str = 'debug', out_dir: str = 'debug'):
        self.page = page
        self.name = name
        self.out_dir = Path(out_dir)
        self.notes = []
        self.bundle_dir = None

    def note(self, msg: str):
        line = f'[{time.strftime("%H:%M:%S")}] {msg}'
        self.notes.append(line)
        print(line, flush=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            return False
        ts = time.strftime('%Y%m%d-%H%M%S')
        self.bundle_dir = self.out_dir / f'{self.name}-{ts}'
        self.bundle_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.page.screenshot(path=str(self.bundle_dir / 'screenshot.png'),
                                 full_page=False)
        except Exception as e:
            self.notes.append(f'截图失败：{e}')
        try:
            (self.bundle_dir / 'dom.html').write_text(
                self.page.content(), encoding='utf-8')
        except Exception as e:
            self.notes.append(f'DOM 保存失败：{e}')
        info = [
            f'时间：{time.strftime("%Y-%m-%d %H:%M:%S")}',
            f'URL：{self._safe(lambda: self.page.url)}',
            f'标题：{self._safe(lambda: self.page.title())}',
            '',
            '--- 操作日志 ---',
            *self.notes,
            '',
            '--- 异常堆栈 ---',
            ''.join(traceback.format_exception(exc_type, exc, tb)),
        ]
        (self.bundle_dir / 'info.txt').write_text('\n'.join(info), encoding='utf-8')
        print(f'\n[诊断包] 已收集失败现场：{self.bundle_dir}', flush=True)
        print('[诊断包] 请把该目录发给开发者用于排错', flush=True)
        return False  # 不吞异常，继续抛出

    @staticmethod
    def _safe(fn):
        try:
            return fn()
        except Exception as e:
            return f'<获取失败：{e}>'
