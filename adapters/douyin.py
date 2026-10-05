"""抖店 / 飞鸽 Playwright 适配器（v0.3）。

实现：扫码登录（保存登录态）/ 轮询新消息 / 发送 / 转人工。
安全：本适配器只做"手脚"，发不发送由上层命令决定；
v0.3 的 poll_douyin 命令全程草稿模式，永不调用 send_message。

关于 SELECTORS：飞鸽工作台 DOM 未经真实环境验证，
字典中的值为占位候选。首次运行失败会自动产出诊断包
（debug/ 目录：截图 + dom.html + info.txt），
把 dom.html 发给开发者即可校准 selector，第二轮即通。
"""
import hashlib
import os
import time
from pathlib import Path

from .base import BaseAdapter, IncomingMessage
from .debug import DebugBundle

WORKBENCH_URL = 'https://fxg.jinritemai.com/'

# 登录态 / 诊断包路径：Docker 里通过环境变量指向 /data 卷（重建不丢）
DEFAULT_STATE_PATH = os.environ.get('DOUYIN_STATE_PATH', 'douyin_state.json')
DEFAULT_DEBUG_DIR = os.environ.get('DOUYIN_DEBUG_DIR', 'debug')

# 登录页 URL 关键词：命中即视为"未登录"
LOGIN_PAGE_KEYWORDS = ('passport', 'login', 'sso', 'auth')

# --- 选择器候选表（待真实环境校准，见模块 docstring）---
SELECTORS = {
    # 登录成功标志（任一命中即认为已登录；为空则只用 URL 启发式判断）
    'login_success': [],
    # 会话列表容器
    'session_list': ['[class*="session"]', '[class*="conversation"]'],
    # 单条会话项
    'session_item': ['[class*="session-item"]', '[class*="conv-item"]'],
    # 会话项内的客户名 / 最后一条消息 / 未读数
    'session_name': ['[class*="name"]', '[class*="nickname"]'],
    'session_last_msg': ['[class*="last-msg"]', '[class*="preview"]'],
    # 消息输入框 / 发送按钮 / 转人工按钮
    'input_box': ['[contenteditable="true"]', 'textarea[class*="input"]'],
    'send_button': ['button[class*="send"]'],
    'transfer_button': ['button[class*="transfer"]', '[class*="转人工"]'],
}

QR_SCREENSHOT = 'qr.png'
LOGIN_WAIT_SECONDS = 180


class DouyinAdapter(BaseAdapter):
    name = 'douyin'

    def __init__(self, storage_state_path=None, headless=True,
                 debug_dir=None):
        self.storage_state_path = Path(storage_state_path or DEFAULT_STATE_PATH)
        self.headless = headless
        self.debug_dir = debug_dir or DEFAULT_DEBUG_DIR
        self._pw = None
        self._browser = None
        self._page = None
        self._seen_ids = set()

    # ---------- 内部 ----------
    def _launch(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self.headless,
            args=['--no-sandbox', '--disable-dev-shm-usage'])

    def _new_page(self):
        if self._browser is None:
            self._launch()
        state = str(self.storage_state_path) if self.storage_state_path.exists() else None
        ctx = self._browser.new_context(storage_state=state)
        self._page = ctx.new_page()
        return self._page

    @staticmethod
    def _is_logged_in(page) -> bool:
        url = page.url.lower()
        if any(k in url for k in LOGIN_PAGE_KEYWORDS):
            return False
        for sel in SELECTORS['login_success']:
            try:
                if page.locator(sel).count() > 0:
                    return True
            except Exception:
                pass
        # login_success 为空时：URL 不含登录关键词即视为已登录
        return not SELECTORS['login_success'] or False

    # ---------- 契约实现 ----------
    def login(self) -> bool:
        """扫码登录：无登录态时截图二维码，用户手机扫码后保存登录态。"""
        page = self._new_page()
        with DebugBundle(page, name='login', out_dir=self.debug_dir) as dbg:
            dbg.note(f'打开飞鸽工作台：{WORKBENCH_URL}')
            page.goto(WORKBENCH_URL, wait_until='domcontentloaded', timeout=60000)
            page.wait_for_timeout(3000)
            if self._is_logged_in(page):
                dbg.note('登录态有效，无需扫码')
                return True
            dbg.note('需要扫码登录，截取二维码…')
            page.screenshot(path=QR_SCREENSHOT)
            print(f'\n请用手机抖音/抖店 App 扫描二维码：{Path(QR_SCREENSHOT).resolve()}', flush=True)
            print(f'等待扫码（{LOGIN_WAIT_SECONDS} 秒超时）…', flush=True)
            deadline = time.time() + LOGIN_WAIT_SECONDS
            while time.time() < deadline:
                page.wait_for_timeout(3000)
                if self._is_logged_in(page):
                    break
            else:
                raise TimeoutError('扫码登录超时，请重试（二维码已刷新请重新截图）')
            self._page.context.storage_state(path=str(self.storage_state_path))
            dbg.note(f'登录成功，登录态已保存：{self.storage_state_path}')
            return True

    def poll_new_messages(self) -> list:
        """轮询会话列表，返回新增的 [IncomingMessage]（内存 + DB 双重去重）。"""
        if self._page is None:
            self.login()
        page = self._page
        with DebugBundle(page, name='poll', out_dir=self.debug_dir) as dbg:
            dbg.note('拉取会话列表…')
            page.goto(WORKBENCH_URL, wait_until='domcontentloaded', timeout=60000)
            page.wait_for_timeout(3000)
            if not self._is_logged_in(page):
                raise RuntimeError('登录态失效，请重新运行 login_douyin 扫码登录')
            raw = self._extract_messages(page, dbg)
            fresh = []
            for m in raw:
                if m.platform_msg_id in self._seen_ids:
                    continue
                self._seen_ids.add(m.platform_msg_id)
                fresh.append(m)
            dbg.note(f'本轮新增 {len(fresh)} 条（原始 {len(raw)} 条）')
            return fresh

    def _extract_messages(self, page, dbg) -> list:
        """按 SELECTORS 候选表提取消息；DOM 对不上时返回空并记日志（触发校准）。"""
        items = page.evaluate(
            """(sels) => {
                const out = [];
                for (const itemSel of sels.session_item) {
                    const nodes = document.querySelectorAll(itemSel);
                    if (!nodes.length) continue;
                    nodes.forEach((el, i) => {
                        const pick = (cands) => {
                            for (const c of cands) {
                                const n = el.querySelector(c);
                                if (n && n.innerText.trim()) return n.innerText.trim();
                            }
                            return '';
                        };
                        const text = pick(sels.session_last_msg) || el.innerText.trim().slice(0, 200);
                        const name = pick(sels.session_name) || ('客户' + i);
                        if (text) out.push({name: name, text: text});
                    });
                    if (out.length) break;
                }
                return out;
            }""",
            {'session_item': SELECTORS['session_item'],
             'session_name': SELECTORS['session_name'],
             'session_last_msg': SELECTORS['session_last_msg']})
        msgs = []
        for it in items:
            mid = 'douyin-' + hashlib.md5(
                f"{it['name']}|{it['text']}".encode()).hexdigest()[:16]
            msgs.append(IncomingMessage(
                platform_msg_id=mid, session_key=it['name'],
                customer_name=it['name'], content=it['text']))
        if not msgs:
            dbg.note('未按候选 selector 提取到消息，dom.html 已保存待校准')
        return msgs

    def send_message(self, session_key: str, content: str) -> bool:
        """向指定会话发送文本。v0.3 不调用（草稿模式），实现供 v0.4 验证。"""
        if self._page is None:
            self.login()
        page = self._page
        with DebugBundle(page, name='send', out_dir=self.debug_dir) as dbg:
            dbg.note(f'发送消息到会话 {session_key}（{len(content)} 字）')
            self._open_session(page, session_key, dbg)
            box = self._first_hit(page, SELECTORS['input_box'], '输入框')
            box.click()
            box.fill(content)
            sent = False
            for sel in SELECTORS['send_button']:
                try:
                    btn = page.locator(sel).first
                    if btn.count():
                        btn.click()
                        sent = True
                        break
                except Exception:
                    continue
            if not sent:
                page.keyboard.press('Enter')  # 兜底：回车发送
            page.wait_for_timeout(1500)
            dbg.note('发送动作已执行')
            return True

    def transfer_to_human(self, session_key: str) -> bool:
        """将会话转给人工。v0.3 不调用，实现供 v0.4 验证。"""
        if self._page is None:
            self.login()
        page = self._page
        with DebugBundle(page, name='transfer', out_dir=self.debug_dir) as dbg:
            dbg.note(f'转人工：{session_key}')
            self._open_session(page, session_key, dbg)
            btn = self._first_hit(page, SELECTORS['transfer_button'], '转人工按钮')
            btn.click()
            page.wait_for_timeout(1500)
            dbg.note('转人工动作已执行（技能组选择待真实环境确认）')
            return True

    # ---------- 小工具 ----------
    def _open_session(self, page, session_key, dbg):
        for sel in SELECTORS['session_item']:
            try:
                items = page.locator(sel)
                for i in range(items.count()):
                    if session_key in items.nth(i).inner_text():
                        items.nth(i).click()
                        page.wait_for_timeout(1500)
                        dbg.note(f'已打开会话：{session_key}')
                        return
            except Exception:
                continue
        raise RuntimeError(f'未找到会话 {session_key}（selector 待校准）')

    @staticmethod
    def _first_hit(page, candidates, what):
        for sel in candidates:
            try:
                loc = page.locator(sel).first
                if loc.count():
                    return loc
            except Exception:
                continue
        raise RuntimeError(f'未找到{what}（selector 待校准，见诊断包 dom.html）')

    def close(self):
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._pw:
            self._pw.stop()
            self._pw = None
        self._page = None
