from contextvars import ContextVar

user_id_ctx = ContextVar("user_id", default=None)
