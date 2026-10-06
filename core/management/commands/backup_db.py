"""备份 SQLite 数据库（用 sqlite3 backup API，热备安全）。

用法：
    python manage.py backup_db
    python manage.py backup_db --dest /path/to/dir
"""
import os
import sqlite3
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = '备份 SQLite 数据库'

    def add_arguments(self, parser):
        parser.add_argument('--dest', default='',
                            help='备份目录（默认与数据库同目录下的 backups/）')

    def handle(self, *args, **opts):
        src = Path(os.environ.get('DB_PATH', settings.DATABASES['default']['NAME']))
        if not src.exists():
            raise FileNotFoundError(f'数据库文件不存在：{src}')
        dest_dir = Path(opts['dest']) if opts['dest'] else src.parent / 'backups'
        dest_dir.mkdir(parents=True, exist_ok=True)
        dst = dest_dir / f'db-{time.strftime("%Y%m%d-%H%M%S")}.sqlite3'
        src_conn = sqlite3.connect(str(src))
        try:
            dst_conn = sqlite3.connect(str(dst))
            try:
                src_conn.backup(dst_conn)
            finally:
                dst_conn.close()
        finally:
            src_conn.close()
        self.stdout.write(self.style.SUCCESS(f'备份完成：{dst}'))
