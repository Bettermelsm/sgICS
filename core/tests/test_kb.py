"""知识库测试：切分 / embedding / 检索 / 入库 / pipeline 注入（全用 fake embedding）。"""
import json
import tempfile
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from core.kb import (
    Retriever, chunk_text, cosine, fake_embed, guess_doc_type, ingest_doc,
)
from core.llm_gateway import BaseLLMGateway
from core.models import KnowledgeChunk, KnowledgeDoc, ShopAccount
from core.pipeline import ReplyPipeline, RuleSet, pipeline_for_shop


class ChunkingTests(TestCase):
    def test_paragraph_split(self):
        # 短段落合并到 size 上限
        chunks = chunk_text('第一段。\n\n第二段。\n\n第三段。', size=500)
        self.assertEqual(chunks, ['第一段。\n第二段。\n第三段。'])
        # size 很小时按段切分
        chunks = chunk_text('第一段。\n\n第二段。\n\n第三段。', size=10, overlap=0)
        self.assertEqual(chunks, ['第一段。\n第二段。', '第三段。'])

    def test_long_text_splits(self):
        text = '\n'.join(f'第{i}段内容填充。' * 30 for i in range(10))
        chunks = chunk_text(text, size=200, overlap=20)
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertLessEqual(len(c), 200)

    def test_empty(self):
        self.assertEqual(chunk_text('   \n  '), [])

    def test_guess_doc_type(self):
        self.assertEqual(guess_doc_type('价格表.xlsx'), 'xlsx')
        self.assertEqual(guess_doc_type('说明.PDF'), 'pdf')
        self.assertEqual(guess_doc_type('未知'), '')


class EmbedSearchTests(TestCase):
    def test_fake_embed_deterministic_and_normalized(self):
        a = fake_embed(['测试文本'])
        b = fake_embed(['测试文本'])
        self.assertEqual(a, b)
        self.assertAlmostEqual(sum(x * x for x in a[0]), 1.0, places=6)

    def test_cosine(self):
        self.assertAlmostEqual(cosine([1, 0], [1, 0]), 1.0)
        self.assertAlmostEqual(cosine([1, 0], [0, 1]), 0.0)

    def test_retrieval_ranking(self):
        shop = ShopAccount.objects.create(name='店', platform='douyin')
        doc = KnowledgeDoc.objects.create(
            shop=shop, title='政策', doc_type='txt', status='ready')
        texts = ['本店商品48小时内发货，快递默认申通',
                 '七天无理由退货，运费由买家承担']
        vecs = fake_embed(texts)
        for i, (t, v) in enumerate(zip(texts, vecs)):
            KnowledgeChunk.objects.create(
                doc=doc, ordering=i, content=t, embedding=json.dumps(v))
        r = Retriever(shop, embed_fn=fake_embed, min_score=0.0)
        hits = r.search('什么时候发货', top_k=2)
        self.assertEqual(len(hits), 2)
        self.assertIn('发货', hits[0][0].content)
        self.assertGreater(hits[0][1], hits[1][1])


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class IngestTests(TestCase):
    def _doc(self, title, name, text):
        shop = ShopAccount.objects.create(name='店', platform='douyin')
        doc = KnowledgeDoc(shop=shop, title=title, doc_type='txt')
        doc.file.save(name, ContentFile(text))
        doc.save()
        return doc

    def test_ingest_txt(self):
        doc = self._doc('t', 't.txt', '发货政策：48小时内发出。\n\n退货政策：七天无理由。\n')
        n = ingest_doc(doc, embed_fn=fake_embed)
        doc.refresh_from_db()
        self.assertEqual(doc.status, 'ready')
        self.assertEqual(doc.chunk_count, n)
        self.assertGreater(n, 0)
        self.assertTrue(KnowledgeChunk.objects.filter(doc=doc)
                        .exclude(embedding='').exists())

    def test_ingest_empty_fails(self):
        doc = self._doc('空', 'e.txt', '   ')
        with self.assertRaises(ValueError):
            ingest_doc(doc, embed_fn=fake_embed)
        doc.refresh_from_db()
        self.assertEqual(doc.status, 'failed')
        self.assertTrue(doc.error)


class RecordingGateway(BaseLLMGateway):
    name = 'rec'

    def __init__(self):
        self.messages = None

    def chat(self, messages):
        self.messages = messages
        return '好的，收到'


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class PipelineKbTests(TestCase):
    def setUp(self):
        self.shop = ShopAccount.objects.create(name='店', platform='douyin')
        self.doc = KnowledgeDoc(shop=self.shop, title='政策', doc_type='txt')
        self.doc.file.save('p.txt', ContentFile('发货政策：本店48小时内发货。\n'))
        self.doc.save()
        ingest_doc(self.doc, embed_fn=fake_embed)

    def _pipeline(self):
        gw = RecordingGateway()
        r = Retriever(self.shop, embed_fn=fake_embed, min_score=0.0)
        return ReplyPipeline(llm=gw, rules=RuleSet(), retriever=r), gw

    def test_ask_with_kb_injects_context(self):
        pipe, gw = self._pipeline()
        reply, hits = pipe.ask_with_kb('什么时候发货？')
        self.assertEqual(reply, '好的，收到')
        self.assertTrue(hits)
        system = gw.messages[0]['content']
        self.assertIn('【资料1】', system)
        self.assertIn('48小时内发货', system)

    def test_handle_ai_branch_mentions_kb(self):
        pipe, _gw = self._pipeline()
        result = pipe.handle('什么时候发货？', [],
                             {'is_transferred': False, 'ai_fail_count': 0})
        self.assertEqual(result.source, 'ai')
        self.assertIn('引用', result.detail)

    def test_pipeline_for_shop_wires_retriever(self):
        pipe = pipeline_for_shop(self.shop, llm=RecordingGateway(),
                                 embed_fn=fake_embed)
        self.assertIsNotNone(pipe.retriever)

    def test_pipeline_for_shop_no_kb(self):
        shop2 = ShopAccount.objects.create(name='空店', platform='douyin')
        pipe = pipeline_for_shop(shop2, llm=RecordingGateway())
        self.assertIsNone(pipe.retriever)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class KbTestViewTests(TestCase):
    def setUp(self):
        User.objects.create_superuser('boss', 'b@x.com', 'pw')
        self.shop = ShopAccount.objects.create(name='店', platform='douyin')
        doc = KnowledgeDoc(shop=self.shop, title='政策', doc_type='txt')
        doc.file.save('p.txt', ContentFile('发货政策：本店48小时内发货。\n'))
        doc.save()
        ingest_doc(doc, embed_fn=fake_embed)
        self.client = Client()
        self.client.force_login(User.objects.get(username='boss'))
        self.url = reverse('admin:core_knowledgedoc_test')

    def test_get_renders(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '知识库测试')

    def test_post_shows_hits_and_answer(self):
        with mock.patch('core.kb.embed_texts', fake_embed):
            r = self.client.post(self.url, {'shop': self.shop.id, 'q': '什么时候发货'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'AI 回答')
        self.assertContains(r, '48小时内发货')

    def test_post_without_key_shows_error(self):
        r = self.client.post(self.url, {'shop': self.shop.id, 'q': '什么时候发货'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '出错')
