"""抖店客服系统（飞鸽工作台）Playwright 适配器（v0.4）。

实现：扫码登录（保存登录态）/ 轮询新消息 / 发送 / 转人工。
安全：本适配器只做"手脚"，发不发送由上层命令决定；
poll_douyin 命令全程草稿模式，永不调用 send_message。

入口（2026-10-05 查证）：fxg.jinritemai.com 已变为抖店官网，
网页版飞鸽改从抖店商家后台右上角进入。真实入口用 DOUYIN_ENTRY_URL
环境变量覆盖；离线验证用 DOUYIN_MOCK_PAGE 指向 mock_workbench.html。

关于 SELECTORS：data-testid 条目对应 Mock 页；真实环境用诊断包
dom.html 校准后追加到各候选列表。
"""
import hashlib
import os
import time
from pathlib import Path

from .base import BaseAdapter, IncomingMessage
from .debug import DebugBundle

WORKBENCH_URL = 'https://fxg.jinritemai.com/'

# 入口说明（2026-10-05 查证）：fxg.jinritemai.com 现已变为抖店官网（商家入驻页），
# 网页版飞鸽改从抖店商家后台右上角进入。真实使用时用 DOUYIN_ENTRY_URL 环境变量覆盖。
ENTRY_URL = os.environ.get('DOUYIN_ENTRY_URL', WORKBENCH_URL)
MOCK_PAGE = os.environ.get('DOUYIN_MOCK_PAGE', '')

# 登录态 / 诊断包路径：Docker 里通过环境变量指向 /data 卷（重建不丢）
DEFAULT_STATE_PATH = os.environ.get('DOUYIN_STATE_PATH', 'douyin_state.json')
DEFAULT_DEBUG_DIR = os.environ.get('DOUYIN_DEBUG_DIR', 'debug')

# 登录页 URL 关键词：命中即视为"未登录"
LOGIN_PAGE_KEYWORDS = ('passport', 'login', 'sso', 'auth')

# --- 选择器候选表 ---
# data-testid 开头的条目对应 adapters/mock_workbench.html（Mock 页）；
# 真实环境用诊断包 dom.html 校准后追加到各候选列表。
SELECTORS = {
    # 两步进入：商家后台右上角「网页版飞鸽」
    'feige_entry': ['[data-testid="feige-entry"]'],
    # 登录成功标志（任一命中即认为已登录；为空则只用 URL 启发式判断）
    'login_success': ['[data-testid="login-ok"]:not([style*="none"])'],
    # Mock 登录遮罩（visible=未登录）
    'login_mask': ['[data-testid="login-mask"]'],
    'mock_scan_button': ['[data-testid="mock-scan"]'],
    # 会话列表容器
    'session_list': ['[data-testid="session-list"]',
                     '[class*="session"]', '[class*="conversation"]'],
    # 单条会话项
    'session_item': ['[data-testid="session-item"]',
                     '[class*="session-item"]', '[class*="conv-item"]'],
    # 会话项内的客户名 / 最后一条消息 / 未读数
    'session_name': ['[data-testid="session-name"]',
                     '[class*="name"]', '[class*="nickname"]'],
    'session_last_msg': ['[data-testid="session-last-msg"]',
                         '[class*="last-msg"]', '[class*="preview"]'],
    # 消息输入框 / 发送按钮 / 转人工按钮
    'input_box': ['[data-testid="input-box"]',
                  '[contenteditable="true"]', 'textarea[class*="input"]'],
    'send_button': ['[data-testid="send-button"]', 'button[class*="send"]'],
    'transfer_button': ['[data-testid="transfer-button"]',
                        'button[class*="transfer"]', '[class*="转人工"]'],
    # 图片发送（v0.8）
    'image_input': ['[data-testid="image-input"]', 'input[type="file"]'],
    'send_image_button': ['[data-testid="image-send-button"]'],
    # 动作记录（Mock 页供断言用）
    'send_log': ['[data-testid="send-log"]'],
    # 登录页二维码（v0.9；真实 DOM 待校准，失败时退化为整页截图）
    'qr_image': ['img[src*="qr"]', 'img[alt*="二维码"]', 'canvas[class*="qr"]',
                 '[class*="qrcode"] img', '[class*="qr-code"]'],
    # 账号密码登录（v0.9；真实 DOM 未验证，候选为启发式，失败看诊断包校准）
    'login_username': ['input[name="account"]', 'input[name="username"]',
                       'input[name="mobile"]', 'input[placeholder*="账号"]',
                       'input[placeholder*="手机"]'],
    'login_password': ['input[type="password"]', 'input[name="password"]'],
    'login_submit': ['button[type="submit"]', '[data-testid="login-submit"]',
                     'button:has-text("登录")'],
}

QR_SCREENSHOT = 'qr.png'
LOGIN_WAIT_SECONDS = 180


def state_path_for_shop(shop_id) -> Path:
    """每店独立的登录态文件；老版本全局文件作为兜底（仅当分店文件不存在时）。"""
    base = Path(DEFAULT_STATE_PATH)
    per_shop = base.parent / f'douyin_state_shop{shop_id}.json'
    if per_shop.exists():
        return per_shop
    if base.exists():
        return base
    return per_shop


class DouyinAdapter(BaseAdapter):
    name = 'douyin'

    def __init__(self, storage_state_path=None, headless=True,
                 debug_dir=None, mock_path=None):
        self.storage_state_path = Path(storage_state_path or DEFAULT_STATE_PATH)
        self.headless = headless
        self.debug_dir = debug_dir or DEFAULT_DEBUG_DIR
        # mock_path：指向 adapters/mock_workbench.html 做离线全流程验证
        self.mock_path = mock_path or MOCK_PAGE or None
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

    def _entry_url(self) -> str:
        if self.mock_path:
            return Path(self.mock_path).resolve().as_uri()
        return ENTRY_URL

    def _is_logged_in(self, page) -> bool:
        if self.mock_path:
            try:
                return not page.locator('[data-testid="login-mask"]').is_visible()
            except Exception:
                return False
        url = page.url.lower()
        if any(k in url for k in LOGIN_PAGE_KEYWORDS):
            return False
        for sel in SELECTORS['login_success']:
            try:
                if page.locator(sel).count() > 0:
                    return True
            except Exception:
                pass
        # 真实环境启发式：URL 不含登录关键词即视为已登录
        # （login_success 的 data-testid 选择器仅 Mock 页有效）
        return True

    def _enter_workbench(self, page, dbg):
        """两步进入：商家后台 → 点「网页版飞鸽」→ 工作台。"""
        url = self._entry_url()
        dbg.note(f'打开入口：{url}')
        page.goto(url, wait_until='domcontentloaded', timeout=60000)
        page.wait_for_timeout(2000)
        entry = self._first_hit(page, SELECTORS['feige_entry'], '「网页版飞鸽」入口')
        if self.mock_path:
            entry.click()
            page.wait_for_timeout(1000)
            return page
        # 真实环境：点击后可能新开标签页
        try:
            with page.context.expect_page(timeout=10000) as new_page_info:
                entry.click()
            new_page = new_page_info.value
            new_page.wait_for_load_state('domcontentloaded', timeout=30000)
            dbg.note('检测到新标签页，已切换')
            self._page = new_page
            return new_page
        except Exception:
            dbg.note('未检测到新标签页，继续当前页')
            page.wait_for_timeout(2000)
            return page

    # ---------- 契约实现 ----------
    def check_login(self) -> bool:
        """轻量登录态检查：只判断，不触发扫码流程。"""
        page = self._new_page()
        with DebugBundle(page, name='check', out_dir=self.debug_dir) as dbg:
            page = self._enter_workbench(page, dbg)
            ok = self._is_logged_in(page)
            dbg.note(f'登录态检查：{"有效" if ok else "失效"}')
            return ok

    def login(self, on_qr=None) -> bool:
        """扫码登录：无登录态时截图二维码，用户手机扫码后保存登录态。
        Mock 模式：点击「模拟扫码登录」按钮。
        on_qr(path)：二维码截图保存后回调（v0.9 后台页面展示用）。"""
        if self.check_login():
            print('登录态有效，无需扫码', flush=True)
            return True
        page = self._page
        with DebugBundle(page, name='login', out_dir=self.debug_dir) as dbg:
            if self.mock_path:
                dbg.note('Mock 模式：点击模拟扫码登录')
                page.locator('[data-testid="mock-scan"]').click()
                page.wait_for_timeout(1000)
            else:
                dbg.note('需要扫码登录，截取二维码…')
                qr_path = self._capture_qr(page, dbg)
                print(f'\n请用手机抖音/抖店 App 扫描二维码：{qr_path}', flush=True)
                if on_qr:
                    on_qr(qr_path)
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

    def _capture_qr(self, page, dbg) -> str:
        """截取登录二维码：优先截二维码元素，失败退化为整页截图。返回截图路径。"""
        qr_path = str(Path(self.debug_dir) / f'qr-{time.strftime("%Y%m%d-%H%M%S")}.png')
        Path(self.debug_dir).mkdir(parents=True, exist_ok=True)
        for sel in SELECTORS['qr_image']:
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    loc.screenshot(path=qr_path)
                    dbg.note(f'二维码已截取（{sel}）')
                    return qr_path
            except Exception:
                continue
        page.screenshot(path=qr_path)
        dbg.note('未定位到二维码元素，已截整页')
        return qr_path

    def login_with_password(self, username: str, password: str) -> bool:
        """账号密码登录（v0.9）。真实登录页 DOM 未验证：选择器为启发式候选，
        失败时诊断包（截图+DOM）会保存，可据此校准 SELECTORS。密码仅本次使用，不保存。"""
        if self.check_login():
            print('登录态有效，无需重复登录', flush=True)
            return True
        page = self._page
        with DebugBundle(page, name='login_password', out_dir=self.debug_dir) as dbg:
            dbg.note('尝试账号密码登录')
            user_input = self._first_hit(page, SELECTORS['login_username'], '账号输入框')
            pwd_input = self._first_hit(page, SELECTORS['login_password'], '密码输入框')
            user_input.fill(username)
            pwd_input.fill(password)
            try:
                btn = self._first_hit(page, SELECTORS['login_submit'], '登录按钮')
                btn.click()
            except Exception:
                dbg.note('未找到登录按钮，改按回车提交')
                pwd_input.press('Enter')
            page.wait_for_timeout(3000)
            if not self._is_logged_in(page):
                raise RuntimeError(
                    '账号密码登录未成功：可能选择器未命中真实登录页，'
                    f'请查看诊断包 {dbg.bundle_dir or self.debug_dir} 校准 SELECTORS')
            self._page.context.storage_state(path=str(self.storage_state_path))
            dbg.note(f'账号登录成功，登录态已保存：{self.storage_state_path}')
            return True

    def logout(self) -> bool:
        """退出登录：删除登录态文件。"""
        p = Path(self.storage_state_path)
        if p.exists():
            p.unlink()
            return True
        return False

    def poll_new_messages(self) -> list:
        """轮询会话列表，返回新增的 [IncomingMessage]（内存 + DB 双重去重）。"""
        if self._page is None:
            self.login()
        with DebugBundle(self._page, name='poll', out_dir=self.debug_dir) as dbg:
            page = self._enter_workbench(self._page, dbg)
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

    def send_image(self, session_key: str, image_path: str) -> bool:
        """向指定会话发送图片。v0.8 新增，Mock 页验证通过。"""
        if self._page is None:
            self.login()
        page = self._page
        with DebugBundle(page, name='send_image', out_dir=self.debug_dir) as dbg:
            dbg.note(f'发送图片到会话 {session_key}：{image_path}')
            self._open_session(page, session_key, dbg)
            file_input = self._first_hit(page, SELECTORS['image_input'], '图片上传框')
            file_input.set_input_files(image_path)
            btn = self._first_hit(page, SELECTORS['send_image_button'], '图片发送按钮')
            btn.click()
            page.wait_for_timeout(1500)
            dbg.note('图片发送动作已执行')
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
