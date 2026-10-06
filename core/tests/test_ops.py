"""运维小功能测试：backup_db + KB 重新入库 action。"""
import sqlite3
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client, TestCase

from core.admin import KnowledgeDocAdmin
from core.models import KnowledgeDoc, ShopAccount


class BackupDbTests(TestCase):
    def test_backup_creates_file(self):
        import os
        src = str(Path(tempfile.mkdtemp()) / 'src.sqlite3')
        conn = sqlite3.connect(src)
        conn.execute('CREATE TABLE t (id INTEGER)')
        conn.commit()
        conn.close()
        dest = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {'DB_PATH': src}):
            call_command('backup_db', dest=dest)
        files = list(Path(dest).glob('db-*.sqlite3'))
        self.assertEqual(len(files), 1)
        conn = sqlite3.connect(str(files[0]))
        try:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")]
            self.assertIn('t', tables)
        finally:
            conn.close()


class ReingestActionTests(TestCase):
    def test_action_calls_ingest(self):
        User.objects.create_superuser('boss', 'b@x.com', 'pw')
        shop = ShopAccount.objects.create(name='店', platform='douyin')
        doc = KnowledgeDoc.objects.create(shop=shop, title='t', doc_type='txt')
        admin = KnowledgeDocAdmin(KnowledgeDoc, None)
        request = mock.Mock()
        admin.message_user = mock.Mock()
        with mock.patch('core.admin.ingest_doc', return_value=3) as m:
            admin.reingest_docs(request, KnowledgeDoc.objects.filter(id=doc.id))
        m.assert_called_once()
        admin.message_user.assert_called()
