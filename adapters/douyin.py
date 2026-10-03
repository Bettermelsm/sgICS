"""Douyin adapter skeleton - Playwright web-automation plan.

Status: skeleton only; real shop integration is step 2.
See README section 5 and the Chinese notes in git history for the full plan.
"""
from .base import BaseAdapter, IncomingMessage


class DouyinAdapter(BaseAdapter):
    name = 'douyin'

    # Feige workbench URL (verify; re-record selectors with Playwright codegen
    # if the DOM changes)
    WORKBENCH_URL = 'https://fxg.jinritemai.com/'

    def __init__(self, storage_state_path='douyin_state.json', headless=False):
        self.storage_state_path = storage_state_path
        self.headless = headless
        self._browser = None
        self._page = None
        self._seen_ids = set()

    def login(self):
        raise NotImplementedError(
            'Step 2: Playwright opens the Feige workbench, manual QR scan, '
            'then save storage_state.')

    def poll_new_messages(self):
        raise NotImplementedError(
            'Step 2: poll the Feige session list DOM, return [IncomingMessage].')

    def send_message(self, session_key, content):
        raise NotImplementedError(
            'Step 2: fill the input box of the target session and send.')

    def transfer_to_human(self, session_key):
        raise NotImplementedError(
            'Step 2: click transfer-to-human and pick a skill group.')

    def close(self):
        if self._browser:
            self._browser.close()
            self._browser = None
