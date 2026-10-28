import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    token: str
    db_path: str
    default_tz: str
    page_size: int
    max_book_bytes: int


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN не задан (см. .env.example)")
    return Config(
        token=token,
        db_path=os.getenv("DB_PATH", "data/bot.sqlite"),
        default_tz=os.getenv("DEFAULT_TZ", "Europe/Moscow"),
        page_size=int(os.getenv("PAGE_SIZE", "1500")),
        max_book_bytes=int(os.getenv("MAX_BOOK_MB", "10")) * 1024 * 1024,
    )
