"""In-memory SSE pub/sub broker.

A user can have multiple subscriber queues (multiple browser tabs).
Single-process design — fine for Package 1 scale (2-30 users).

Three publish modes:
- publish_to(user_ids, ...): personal events to specific users
- publish_broadcast(...): all online users
- publish_to_others(except_user, ...): everyone except one user (for own actions)
"""
import asyncio
from dataclasses import dataclass
from typing import Iterable


@dataclass
class SSEEvent:
    event_type: str
    data: dict


class SSEBroker:
    def __init__(self) -> None:
        self._subscribers: dict[int, list[asyncio.Queue]] = {}

    def subscribe(self, user_id: int) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.setdefault(user_id, []).append(queue)
        return queue

    def unsubscribe(self, user_id: int, queue: asyncio.Queue) -> None:
        queues = self._subscribers.get(user_id, [])
        if queue in queues:
            queues.remove(queue)
        if not queues and user_id in self._subscribers:
            del self._subscribers[user_id]

    def online_user_ids(self) -> set[int]:
        return set(self._subscribers.keys())

    async def publish_to(
        self, user_ids: Iterable[int], event_type: str, data: dict
    ) -> None:
        event = SSEEvent(event_type=event_type, data=data)
        for uid in user_ids:
            for q in list(self._subscribers.get(uid, [])):
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    # Slow consumer — drop
                    pass

    async def publish_broadcast(self, event_type: str, data: dict) -> None:
        await self.publish_to(self._subscribers.keys(), event_type, data)

    async def publish_to_others(
        self, except_user_id: int, event_type: str, data: dict
    ) -> None:
        targets = [uid for uid in self._subscribers if uid != except_user_id]
        await self.publish_to(targets, event_type, data)


# Module-level singleton (FastAPI app uses this)
broker = SSEBroker()
