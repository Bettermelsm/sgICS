"""引导卡片单测：卡片数据 + Admin 首页渲染。"""
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from core.context_processors import workbench_guide
from core.models import KeywordRule, ShopAccount


def fake_request(path='/admin/'):
    rf = RequestFactory()
    return rf.get(path)


class GuideCardsTests(TestCase):
    def test_four_cards_with_required_keys(self):
        cards = workbench_guide(fake_request())['guide_cards']
        self.assertEqual(len(cards), 4)
        for c in cards:
            for k in ('num', 'title', 'desc', 'status', 'done', 'url', 'action'):
                self.assertIn(k, c)
        self.assertEqual([c['num'] for c in cards], ['01', '02', '03', '04'])

    def test_empty_state(self):
        cards = workbench_guide(fake_request())['guide_cards']
        self.assertFalse(any(c['done'] for c in cards))
        self.assertIn('还没建店', cards[0]['status'])

    def test_done_state_reflects_db(self):
        shop = ShopAccount.objects.create(name='店', platform='douyin')
        KeywordRule.objects.create(shop=shop, keywords='发货', reply='r')
        cards = workbench_guide(fake_request())['guide_cards']
        self.assertTrue(cards[0]['done'])
        self.assertIn('1 家店铺', cards[0]['status'])
        self.assertTrue(cards[1]['done'])

    def test_not_on_non_admin_paths(self):
        self.assertEqual(workbench_guide(fake_request('/')), {})

    def test_admin_index_renders_cards(self):
        User.objects.create_superuser('admin', 'a@b.com', 'pw')
        self.client.force_login(User.objects.get(username='admin'))
        resp = self.client.get('/admin/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '工作台使用指南')
        for title in ('建店铺', '配话术', '接飞鸽', '收草稿'):
            self.assertContains(resp, title)
