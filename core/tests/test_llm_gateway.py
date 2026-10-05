"""GLM 网关单测：中文错误、超时重试、ping（全部 mock，不调真实接口）。"""
import os
from unittest import mock

import openai as openai_pkg
from django.test import SimpleTestCase

from core.llm_gateway import GLMGateway, GLMError


def _resp(text='你好呀'):
    m = mock.MagicMock()
    m.chat.completions.create.return_value.choices = [
        mock.MagicMock(message=mock.MagicMock(content=text))]
    return m


def _gw(**kwargs):
    kwargs.setdefault('api_key', 'test-key')
    kwargs.setdefault('max_retries', 1)
    return GLMGateway(**kwargs)


class GLMGatewayTest(SimpleTestCase):
    def test_missing_key(self):
        with mock.patch.dict(os.environ, {'ZHIPU_API_KEY': ''}):
            with self.assertRaises(ValueError) as ctx:
                GLMGateway()
            self.assertIn('ZHIPU_API_KEY', str(ctx.exception))

    def test_chat_ok(self):
        with mock.patch.object(openai_pkg, 'OpenAI', return_value=_resp('ok')):
            self.assertEqual(_gw().chat([{'role': 'user', 'content': 'hi'}]), 'ok')

    def test_auth_error_chinese(self):
        err = openai_pkg.AuthenticationError('bad key',
                                             response=mock.MagicMock(), body=None)
        with mock.patch.object(openai_pkg, 'OpenAI', return_value=_resp()) as m:
            m.chat.completions.create.side_effect = err
            with self.assertRaises(GLMError) as ctx:
                _gw().chat([])
            self.assertIn('API Key 无效', str(ctx.exception))

    def test_rate_limit_chinese(self):
        err = openai_pkg.RateLimitError('slow down',
                                        response=mock.MagicMock(), body=None)
        with mock.patch.object(openai_pkg, 'OpenAI', return_value=_resp()) as m:
            m.chat.completions.create.side_effect = err
            with self.assertRaises(GLMError) as ctx:
                _gw().chat([])
            self.assertIn('限流', str(ctx.exception))

    def test_timeout_retry_then_ok(self):
        req = mock.MagicMock()
        client = _resp('recovered')
        client.chat.completions.create.side_effect = [
            openai_pkg.APITimeoutError(req), client.chat.completions.create.return_value]
        with mock.patch.object(openai_pkg, 'OpenAI', return_value=client):
            with mock.patch('core.llm_gateway.time.sleep'):
                self.assertEqual(_gw().chat([]), 'recovered')
            self.assertEqual(client.chat.completions.create.call_count, 2)

    def test_timeout_twice_raises(self):
        req = mock.MagicMock()
        client = _resp()
        client.chat.completions.create.side_effect = openai_pkg.APITimeoutError(req)
        with mock.patch.object(openai_pkg, 'OpenAI', return_value=client):
            with mock.patch('core.llm_gateway.time.sleep'):
                with self.assertRaises(GLMError) as ctx:
                    _gw(max_retries=1).chat([])
                self.assertIn('超时', str(ctx.exception))

    def test_empty_reply(self):
        with mock.patch.object(openai_pkg, 'OpenAI', return_value=_resp('  ')):
            with self.assertRaises(GLMError) as ctx:
                _gw().chat([])
            self.assertIn('空回复', str(ctx.exception))

    def test_ping_ok(self):
        with mock.patch.object(openai_pkg, 'OpenAI', return_value=_resp('pong')):
            ok, ms, msg = _gw().ping()
            self.assertTrue(ok)
            self.assertGreaterEqual(ms, 0)
            self.assertEqual(msg, 'pong')

    def test_ping_fail(self):
        err = openai_pkg.AuthenticationError('bad', response=mock.MagicMock(), body=None)
        with mock.patch.object(openai_pkg, 'OpenAI', return_value=_resp()) as m:
            m.chat.completions.create.side_effect = err
            ok, ms, msg = _gw().ping()
            self.assertFalse(ok)
            self.assertIn('API Key 无效', msg)
