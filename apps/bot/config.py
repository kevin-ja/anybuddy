from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    discord_bot_token: str = Field(alias="DISCORD_BOT_TOKEN")
    fastapi_url: str = Field(alias="FASTAPI_URL", default="http://api:8000/chat")
    allowed_channels: str = Field(alias="ALLOWED_CHANNELS")


settings = Settings()