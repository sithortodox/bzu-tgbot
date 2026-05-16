from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BOT_TOKEN: str
    DATABASE_URL: str = "postgresql+psycopg2://bzubot:bzubot@localhost:5432/bzubot"
    REDIS_URL: str = "redis://localhost:6379/0"
    ADMIN_IDS: list[int] = []
    MONTH_PRICE: int = 49900
    THREE_MONTHS_PRICE: int = 129000
    PROVIDER_TOKEN: str = ""

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, str):
            return [int(x.strip()) for x in v.strip("[]").split(",") if x.strip()]
        if isinstance(v, (int, float)):
            return [int(v)]
        return v

    @property
    def month_price_rub(self) -> int:
        return self.MONTH_PRICE

    @property
    def three_months_price_rub(self) -> int:
        return self.THREE_MONTHS_PRICE

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
