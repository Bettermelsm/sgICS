"""一键检查 GLM 连通性：验证 Key、模型名、往返延迟。

用法：
    python manage.py check_glm
"""
from django.core.management.base import BaseCommand, CommandError

from core.llm_gateway import GLMGateway


class Command(BaseCommand):
    help = '检查智谱 GLM 连通性（需要 .env 中配置 ZHIPU_API_KEY）'

    def handle(self, *args, **options):
        try:
            gw = GLMGateway()
        except ValueError as e:
            raise CommandError(str(e))
        self.stdout.write(f'网关：{gw.name} ｜ 模型：{gw.model}')
        self.stdout.write('正在发送测试消息…')
        ok, ms, msg = gw.ping()
        if ok:
            self.stdout.write(self.style.SUCCESS(f'连通正常，往返 {ms}ms'))
            self.stdout.write(f'模型回复：{msg}')
        else:
            raise CommandError(f'连通失败：{msg}')
