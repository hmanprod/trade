import logging
from collections import deque
from datetime import datetime, timezone

from telethon import events

from app.telegram.client import multi_telethon_manager

logger = logging.getLogger(__name__)

_dedup_cache: set[int] = set()
DEDUP_MAX_SIZE = 10000
_event_handlers: dict[int, object] = {}

# Debug d'exécution en mémoire (dernière exécution / session en cours)
LOG_MAX_LINES = 200
_run_log: deque[str] = deque(maxlen=LOG_MAX_LINES)
_run_stats: dict[str, int] = {"received": 0, "forwarded": 0, "filtered": 0, "skip": 0, "errors": 0}
_run_started_at: datetime | None = None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def reset_run():
    global _run_started_at
    _run_log.clear()
    _run_stats.update({"received": 0, "forwarded": 0, "filtered": 0, "skip": 0, "errors": 0})
    _run_started_at = datetime.now(timezone.utc)


def get_run_debug() -> dict:
    return {
        "stats": dict(_run_stats),
        "lines": list(_run_log),
        "started_at": _run_started_at.isoformat() if _run_started_at else None,
    }


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
    reset_run()
    _run_log.append(f"{_now()} — Démarrage du relais ({len(source_group_ids)} compte(s) avec sources)")
    for session_id, client in multi_telethon_manager.get_all():
        group_ids = source_group_ids.get(session_id, [])
        if not group_ids:
            continue

        session_dests = dest_map.get(session_id, {})

        async def handler(event: events.NewMessage.Event, _sid=session_id, _gids=group_ids, _dests=session_dests):
            msg = event.message
            _run_stats["received"] += 1
            if not msg or not msg.chat_id:
                return

            if msg.chat_id not in _gids:
                return

            if _check_and_cache(msg.id, msg.chat_id):
                return

            _run_log.append(f"{_now()} — Reçu de chat {msg.chat_id} (id {msg.id})")
            if keywords:
                text = msg.text or ""
                if not any(kw.lower() in text.lower() for kw in keywords):
                    _run_stats["filtered"] += 1
                    _run_log.append(f"{_now()} — Filtré (mot-clé) : chat {msg.chat_id}, id {msg.id}")
                    return

            dest_id = _dests.get(msg.chat_id)
            if dest_id is None:
                _run_stats["skip"] += 1
                _run_log.append(f"{_now()} — Skip (pas de destination) : chat {msg.chat_id}, id {msg.id}")
                return

            cl = multi_telethon_manager.get(_sid)
            if cl:
                try:
                    await cl.forward_messages(dest_id, messages=msg.id, from_peer=msg.chat_id)
                    _run_stats["forwarded"] += 1
                    _run_log.append(f"{_now()} — Forward chat {msg.chat_id} → {dest_id} (id {msg.id})")
                except Exception as e:
                    _run_stats["errors"] += 1
                    _run_log.append(f"{_now()} — Erreur forward : {type(e).__name__}: {e}")
                    logger.exception("Forward failed chat=%s dest=%s", msg.chat_id, dest_id)

        client.add_event_handler(handler, events.NewMessage)
        _event_handlers[session_id] = handler


async def stop_relay():
    for session_id, client in multi_telethon_manager.get_all():
        handler = _event_handlers.pop(session_id, None)
        if handler:
            client.remove_event_handler(handler)
    _dedup_cache.clear()
