from os import getenv
from dotenv import load_dotenv

load_dotenv()


def _parse_admin_ids(raw: str) -> list[int]:
    """Парсит строку '123,456,789' в список [123, 456, 789]."""
    if not raw:
        return []
    result = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            try:
                result.append(int(part))
            except ValueError:
                pass
    return result


class Config:
    BOT_TOKEN: str = getenv("BOT_TOKEN", "")
    ADMIN_GROUP_ID: int = int(getenv("ADMIN_GROUP_ID", "0"))
    ORDERS_THREAD_ID: int = int(getenv("ORDERS_THREAD_ID", "0"))
    ADMIN_USER_IDS: list[int] = _parse_admin_ids(getenv("ADMIN_USER_IDS", ""))

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.ADMIN_USER_IDS

    def validate(self) -> None:
        if not self.BOT_TOKEN:
            raise ValueError("BOT_TOKEN не задан в .env")
        if not self.ADMIN_GROUP_ID:
            raise ValueError("ADMIN_GROUP_ID не задан в .env")
        if not self.ADMIN_USER_IDS:
            raise ValueError("ADMIN_USER_IDS не задан в .env (укажите хотя бы один ID)")


config = Config()
config.validate()