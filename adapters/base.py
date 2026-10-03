"""平台适配器契约：所有平台（抖店/拼多多/千牛…）都实现这个接口。

这是原项目闭源 __main__.exe 所承担职责的开源替代设计：
登录 / 收消息 / 发消息 / 转人工 四个动作，平台差异收敛在子类里，
上层的回复流水线完全不用关心平台。
"""
from dataclasses import dataclass


@dataclass
class IncomingMessage:
    platform_msg_id: str   # 平台原生消息 ID，用于去重
    session_key: str       # 会话标识（客户ID）
    customer_name: str
    content: str
    msg_type: str = 'text'  # text / image / ...


class BaseAdapter:
    name = 'base'

    def login(self) -> bool:
        """登录平台工作台。返回是否成功。"""
        raise NotImplementedError

    def poll_new_messages(self) -> list:
        """拉取自上次以来的新消息，返回 [IncomingMessage]。"""
        raise NotImplementedError

    def send_message(self, session_key: str, content: str) -> bool:
        """向指定会话发送文本消息。"""
        raise NotImplementedError

    def transfer_to_human(self, session_key: str) -> bool:
        """将会话转给人工客服。"""
        raise NotImplementedError

    def close(self):
        """释放资源（关浏览器等）。"""
