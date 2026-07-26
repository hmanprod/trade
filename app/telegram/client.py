from telethon import TelegramClient

from app.config import settings


class TelethonManager:
    _client: TelegramClient | None = None
    _phone: str | None = None

    async def create_client(self) -> TelegramClient:
        self._client = TelegramClient(
            session=":memory:",
            api_id=settings.telegram_api_id,
            api_hash=settings.telegram_api_hash,
        )
        return self._client

    async def restore(self, session_str: str) -> TelegramClient:
        self._client = TelegramClient(
            session=session_str,
            api_id=settings.telegram_api_id,
            api_hash=settings.telegram_api_hash,
        )
        await self._client.connect()
        return self._client

    async def disconnect(self):
        if self._client and self._client.is_connected():
            await self._client.disconnect()
        self._client = None

    @property
    def client(self) -> TelegramClient | None:
        return self._client

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected()

    @property
    def phone(self) -> str | None:
        return self._phone

    @phone.setter
    def phone(self, value: str):
        self._phone = value


telethon_manager = TelethonManager()
