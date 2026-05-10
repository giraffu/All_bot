import logging

logger = logging.getLogger(__name__)

CALLBACK_ROUTES = {}
SORTED_ROUTES = []


def register_callback(prefix: str):
    """
    Decorator to register a callback handler for a specific data prefix.
    """

    def decorator(func):
        if prefix in CALLBACK_ROUTES:
            logger.warning(f"Overwriting callback route for prefix: {prefix}")
        CALLBACK_ROUTES[prefix] = func

        # 每次注册时动态更新排序缓存，按前缀长度降序，避免短前缀劫持长前缀
        global SORTED_ROUTES
        SORTED_ROUTES = sorted(CALLBACK_ROUTES.keys(), key=len, reverse=True)
        return func

    return decorator
