from telethon import TelegramClient

from app.config import settings


class MultiTelethonManager:
    _clients: dict[int, TelegramClient] = {}
    _phones: dict[int, str] = {}

    async def add(self, session_id: int, client: TelegramClient, phone: str):
        self._clients[session_id] = client
        self._phones[session_id] = phone

    async def remove(self, session_id: int):
        client = self._clients.pop(session_id, None)
        self._phones.pop(session_id, None)
        if client and client.is_connected():
            await client.disconnect()

    def get(self, session_id: int) -> TelegramClient | None:
        return self._clients.get(session_id)

    def phone(self, session_id: int) -> str | None:
        return self._phones.get(session_id)

    def get_all(self) -> list[tuple[int, TelegramClient]]:
        return [(sid, c) for sid, c in self._clients.items()]

    async def disconnect_all(self):
        for client in self._clients.values():
            if client and client.is_connected():
                await client.disconnect()
        self._clients.clear()
        self._phones.clear()

    def is_connected(self, session_id: int) -> bool:
        client = self._clients.get(session_id)
        return client is not None and client.is_connected()

    def connected_count(self) -> int:
        return sum(1 for c in self._clients.values() if c.is_connected())

    @property
    def total_count(self) -> int:
        return len(self._clients)


multi_telethon_manager = MultiTelethonManager()
