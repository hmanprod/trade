import logging

from telethon import events

from app.telegram.client import multi_telethon_manager

logger = logging.getLogger(__name__)

_dedup_cache: set[int] = set()
DEDUP_MAX_SIZE = 10000
_event_handlers: dict[int, object] = {}


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


async def start_relay(source_group_ids: dict[int, list[int]], dest_map: dict[int, dict[int, int]], keywords: list[str] | None = None):
    for session_id, client in multi_telethon_manager.get_all():
        group_ids = source_group_ids.get(session_id, [])
        if not group_ids:
            continue

        session_dests = dest_map.get(session_id, {})

        async def handler(event: events.NewMessage.Event, _sid=session_id, _gids=group_ids, _dests=session_dests):
            msg = event.message
            if not msg or not msg.chat_id:
                return

            if msg.chat_id not in _gids:
                return

            if _check_and_cache(msg.id, msg.chat_id):
                return

            if keywords:
                text = msg.text or ""
                if not any(kw.lower() in text.lower() for kw in keywords):
                    return

            dest_id = _dests.get(msg.chat_id)
            if dest_id is None:
                logger.info("Skipping msg %s from chat %s: no destination set", msg.id, msg.chat_id)
                return

            cl = multi_telethon_manager.get(_sid)
            if cl:
                logger.info("Forwarding msg %s from chat %s to %s", msg.id, msg.chat_id, dest_id)
                await cl.forward_messages(dest_id, messages=msg.id, from_peer=msg.chat_id)

        client.add_event_handler(handler, events.NewMessage)
        _event_handlers[session_id] = handler


async def stop_relay():
    for session_id, client in multi_telethon_manager.get_all():
        handler = _event_handlers.pop(session_id, None)
        if handler:
            client.remove_event_handler(handler)
    _dedup_cache.clear()
