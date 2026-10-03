"""LLM 网关：统一的对话接口，GLM 走智谱 OpenAI 兼容接口。

设计要点：
- BaseLLMGateway 定义契约，换模型厂商只需新增子类；
- MockGateway 无需 Key，用于离线演示流水线；
- GLMGateway 用官方 openai 包直连 https://open.bigmodel.cn/api/paas/v4/。
"""
import os


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
                 base_url: str = '', timeout: int = 60):
        self.api_key = api_key or os.environ.get('ZHIPU_API_KEY', '')
        # 模型名以智谱控制台当前可用为准，可用环境变量 GLM_MODEL 覆盖
        self.model = model or os.environ.get('GLM_MODEL', 'glm-4-flash')
        self.base_url = base_url or os.environ.get(
            'ZHIPU_BASE_URL', 'https://open.bigmodel.cn/api/paas/v4/')
        self.timeout = timeout
        if not self.api_key:
            raise ValueError('缺少 ZHIPU_API_KEY：请在 .env 中配置后再使用 GLMGateway')

    def chat(self, messages: list) -> str:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout)
        resp = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
            max_tokens=800,
        )
        return (resp.choices[0].message.content or '').strip()


def build_gateway() -> BaseLLMGateway:
    """按环境变量自动选择：有 Key 用 GLM，否则用 Mock（离线演示）。"""
    if os.environ.get('ZHIPU_API_KEY'):
        return GLMGateway()
    return MockGateway()
