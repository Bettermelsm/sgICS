"""LLM 网关：统一的对话接口，GLM 走智谱 OpenAI 兼容接口。

设计要点：
- BaseLLMGateway 定义契约，换模型厂商只需新增子类；
- MockGateway 无需 Key，用于离线演示流水线；
- GLMGateway 用官方 openai 包直连 https://open.bigmodel.cn/api/paas/v4/，
  带中文错误信息与超时重试，便于一线排查。
"""
import os
import time


class GLMError(Exception):
    """网关调用失败（已翻译为中文，可直接展示）。"""


class BaseLLMGateway:
    name = 'base'

    def chat(self, messages: list) -> str:
        """messages: [{'role': 'system'|'user'|'assistant', 'content': str}]"""
        raise NotImplementedError


class MockGateway(BaseLLMGateway):
    """离线演示用：不调任何外部接口。"""

    name = 'mock'

    def __init__(self, reply: str = '（模拟AI回复）收到您的咨询，正在为您查询，请稍候~'):
        self._reply = reply

    def chat(self, messages: list) -> str:
        return self._reply


class GLMGateway(BaseLLMGateway):
    """智谱 GLM：OpenAI 兼容接口。"""

    name = 'glm'

    def __init__(self, api_key: str = '', model: str = '',
                 base_url: str = '', timeout: int = 60, max_retries: int = 1):
        self.api_key = api_key or os.environ.get('ZHIPU_API_KEY', '')
        # 模型名以智谱控制台当前可用为准，可用环境变量 GLM_MODEL 覆盖
        self.model = model or os.environ.get('GLM_MODEL', 'glm-4-flash')
        self.base_url = base_url or os.environ.get(
            'ZHIPU_BASE_URL', 'https://open.bigmodel.cn/api/paas/v4/')
        self.timeout = timeout
        self.max_retries = max_retries
        if not self.api_key:
            raise ValueError('缺少 ZHIPU_API_KEY：请在 .env 中配置后再使用 GLMGateway')

    def ping(self) -> tuple:
        """连通性检查。返回 (ok: bool, latency_ms: int, message: str)。"""
        start = time.time()
        try:
            reply = self.chat([{'role': 'user', 'content': '你好，请用一句话介绍你自己。'}])
            ms = int((time.time() - start) * 1000)
            return True, ms, reply
        except GLMError as e:
            ms = int((time.time() - start) * 1000)
            return False, ms, str(e)

    def chat(self, messages: list) -> str:
        from openai import OpenAI
        import openai as openai_pkg

        client = OpenAI(api_key=self.api_key, base_url=self.base_url,
                        timeout=self.timeout, max_retries=0)
        last_err = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=800,
                )
                text = (resp.choices[0].message.content or '').strip()
                if not text:
                    raise GLMError('模型返回了空回复，请重试')
                return text
            except GLMError:
                raise
            except openai_pkg.AuthenticationError:
                raise GLMError('API Key 无效或已过期：请检查 .env 中的 ZHIPU_API_KEY')
            except openai_pkg.RateLimitError:
                raise GLMError('触发限流：请稍后重试，或检查 Key 的配额')
            except (openai_pkg.APITimeoutError, openai_pkg.APIConnectionError) as e:
                last_err = e
                if attempt < self.max_retries:
                    time.sleep(1)
                    continue
                raise GLMError(f'连接超时（已重试 {self.max_retries} 次）：请检查网络后重试')
            except openai_pkg.APIError as e:
                raise GLMError(f'接口返回错误：{e}')
            except Exception as e:
                raise GLMError(f'调用失败：{e}')
        raise GLMError(f'调用失败：{last_err}')


def build_gateway() -> BaseLLMGateway:
    """按环境变量自动选择：有 Key 用 GLM，否则用 Mock（离线演示）。"""
    if os.environ.get('ZHIPU_API_KEY'):
        return GLMGateway()
    return MockGateway()
