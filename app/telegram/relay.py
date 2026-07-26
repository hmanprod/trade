from telethon import events

from app.telegram.client import telethon_manager

_dedup_cache: set[int] = set()
DEDUP_MAX_SIZE = 10000


def _dedup_key(msg_id: int, chat_id: int) -> int:
    return chat_id * 2**32 + msg_id


def _check_and_cache(msg_id: int, chat_id: int) -> bool:
    key = _dedup_key(msg_id, chat_id)
    if key in _dedup_cache:
        return True
    _dedup_cache.add(key)
    if len(_dedup_cache) > DEDUP_MAX_SIZE:
        _dedup_cache.pop()
    return False


async def start_relay(source_group_ids: list[int], destination_id: int, keywords: list[str] | None = None):
    client = telethon_manager.client
    if not client:
        return

    async def handler(event: events.NewMessage.Event):
        msg = event.message
        if not msg or not msg.chat_id:
            return

        if msg.chat_id not in source_group_ids:
            return

        if _check_and_cache(msg.id, msg.chat_id):
            return

        if keywords:
            text = msg.text or ""
            if not any(kw.lower() in text.lower() for kw in keywords):
                return

        await client.forward_messages(destination_id, messages=msg.id, from_peer=msg.chat_id)

    client.add_event_handler(handler, events.NewMessage)


async def stop_relay():
    if telethon_manager.client:
        telethon_manager.client.remove_event_handler(...)
    _dedup_cache.clear()
