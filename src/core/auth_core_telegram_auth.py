from dataclasses import dataclass


@dataclass(slots=True)
class TelegramAuthProfile:
    tg_id: int | None
    username: str
    full_name: str
    language_code: str | None


def build_telegram_auth_profile(user_data: dict) -> TelegramAuthProfile:
    first_name = user_data.get("first_name", "")
    last_name = user_data.get("last_name", "")

    full_name = first_name
    if last_name:
        full_name += f" {last_name}"

    return TelegramAuthProfile(
        tg_id=user_data.get("id"),
        username=user_data.get("username", ""),
        full_name=full_name.strip(),
        language_code=user_data.get("language_code"),
    )
