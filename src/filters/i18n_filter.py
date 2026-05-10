from typing import List, Union
from telegram.ext.filters import MessageFilter
from telegram import Message


class I18nFilter(MessageFilter):
    """
    无状态的多语言过滤器 (PTB 最佳实践)。
    用于在 FSM entry_points 中安全、O(1) 地匹配多语言按钮。
    """

    def __init__(self, i18n_keys: Union[str, List[str]]):
        super().__init__()
        # 支持传入单键或多键列表，内部转为 Set 以实现 O(1) 查询
        if isinstance(i18n_keys, str):
            self.i18n_keys = {i18n_keys}
        else:
            self.i18n_keys = set(i18n_keys)

    def filter(self, message: Message) -> bool:
        # 防御性判断：防止纯图片等无文本消息引发异常
        if not message.text:
            return False

        from src.handlers.prompt_router import GLOBAL_REVERSE_MAP

        # 极速 O(1) 拦截：判断当前消息文本反向映射的 key 是否在允许的集合内
        route_key = GLOBAL_REVERSE_MAP.get(message.text)
        return route_key in self.i18n_keys
