"""适配器演示：对 Mock 工作台跑通 登录→轮询→发送→转人工 全流程。

用法：
    python manage.py demo_adapter --mock     # 离线演示（Docker 里可跑）
    python manage.py demo_adapter            # 真实环境（需配 DOUYIN_ENTRY_URL）

真实环境只演示到轮询（不发送）；Mock 环境全流程演示。
"""
from pathlib import Path

from django.core.management.base import BaseCommand

from adapters.douyin import DouyinAdapter

MOCK_PAGE = Path(__file__).resolve().parent.parent.parent.parent / 'adapters' / 'mock_workbench.html'


class Command(BaseCommand):
    help = '适配器全流程演示（Mock 页离线可跑）'

    def add_arguments(self, parser):
        parser.add_argument('--mock', action='store_true', help='使用 Mock 工作台')

    def handle(self, *args, **opts):
        mock_path = str(MOCK_PAGE) if opts['mock'] else None
        adapter = DouyinAdapter(mock_path=mock_path)
        try:
            self.stdout.write('1) 登录…')
            assert adapter.login(), '登录失败'
            self.stdout.write(self.style.SUCCESS('   登录成功'))

            self.stdout.write('2) 轮询新消息…')
            msgs = adapter.poll_new_messages()
            for m in msgs:
                self.stdout.write(f'   [{m.customer_name}] {m.content} (id={m.platform_msg_id})')
            if not msgs:
                self.stdout.write('   （无新消息）')

            if opts['mock'] and msgs:
                self.stdout.write('3) 发送测试…')
                adapter.send_message(msgs[0].session_key, '您好，这里是演示回复~')
                self.stdout.write(self.style.SUCCESS('   发送动作已执行'))
                if len(msgs) > 1:
                    self.stdout.write('4) 转人工测试…')
                    adapter.transfer_to_human(msgs[1].session_key)
                    self.stdout.write(self.style.SUCCESS('   转人工动作已执行'))
                log = adapter._page.locator('[data-testid="send-log"]').inner_text()
                self.stdout.write(f'   Mock 记录：{log.strip().replace(chr(10), " | ")}')
            elif not opts['mock']:
                self.stdout.write('   真实环境演示到此为止（不发送）。')
            self.stdout.write(self.style.SUCCESS('演示完成。'))
        finally:
            adapter.close()
