from typing import Union, List, Set
from telegram.ext.filters import MessageFilter
from telegram import Message

class I18nFilter(MessageFilter):
    """
    A filter that matches incoming message text against the O(1) GLOBAL_REVERSE_MAP
    to determine if it corresponds to specific i18n keys.
    """
    def __init__(self, i18n_keys: Union[str, List[str]]):
        super().__init__()
        if isinstance(i18n_keys, str):
            self.i18n_keys: Set[str] = {i18n_keys}
        else:
            self.i18n_keys: Set[str] = set(i18n_keys)

    def filter(self, message: Message) -> bool:
        if not message.text:
            return False
            
        from src.handlers.prompt_router import GLOBAL_REVERSE_MAP
        matched_key = GLOBAL_REVERSE_MAP.get(message.text)
        return matched_key in self.i18n_keys
