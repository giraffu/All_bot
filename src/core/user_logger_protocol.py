from typing import Any, Protocol


class UserLoggerProtocol(Protocol):
    user_id: int
    username: str | None

    def save_input_image(self, path: str) -> str:
        ...

    def save_output_image(self, *args: Any, **kwargs: Any) -> str:
        ...

    async def log_task(self, *args: Any, **kwargs: Any) -> Any:
        ...
