"""Server-Sent Events broker for the staff and doctor screens. Sync endpoints (threadpool) publish; the async stream endpoint
subscribes. Events carry tokens and short labels only, never answers or doses. Help requests are kept here in memory."""
import asyncio
import itertools
import json
import threading
from datetime import datetime
from typing import Optional

EVENT_TYPES = ("patient.updated", "redflag.triggered", "help.requested", "queue.changed")


class Broker:
    def __init__(self, max_queue: int = 256):
        self._subs: set[asyncio.Queue] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self.max_queue = max_queue

    def publish(self, type_: str, data: dict) -> None:
        if type_ not in EVENT_TYPES:
            raise ValueError(type_)
        msg = {"id": next(self._ids), "type": type_, "data": data}
        with self._lock:
            loop, subs = self._loop, list(self._subs)
        if loop is None or not subs:
            return
        for q in subs:
            loop.call_soon_threadsafe(self._put, q, msg)

    @staticmethod
    def _put(q: asyncio.Queue, msg: dict) -> None:
        if q.full():                      # a stalled client drops its oldest event; the UI also polls every 10 s as a fallback
            q.get_nowait()
        q.put_nowait(msg)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(self.max_queue)
        with self._lock:
            self._loop = asyncio.get_running_loop()
            self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            self._subs.discard(q)

    @property
    def subscribers(self) -> int:
        return len(self._subs)


def sse_format(msg: dict) -> str:
    return f"id: {msg['id']}\nevent: {msg['type']}\ndata: {json.dumps(msg['data'], ensure_ascii=False)}\n\n"


class HelpRequests:
    """'Patient needs help' alerts raised from the kiosk; staff dismiss them. In memory only."""

    def __init__(self):
        self._items: list[dict] = []
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def add(self, token: str) -> dict:
        with self._lock:
            for it in self._items:           # one open request per token: a second tap refreshes the time
                if it["token"] == token and not it["dismissed"]:
                    it["at"] = datetime.now().astimezone().isoformat(timespec="seconds")
                    return dict(it)
            it = {"id": next(self._ids), "token": token, "at": datetime.now().astimezone().isoformat(timespec="seconds"), "dismissed": False}
            self._items.append(it)
            return dict(it)

    def open(self) -> list[dict]:
        with self._lock:
            return [dict(i) for i in self._items if not i["dismissed"]]

    def dismiss(self, rid: int, by: str) -> bool:
        with self._lock:
            for it in self._items:
                if it["id"] == rid and not it["dismissed"]:
                    it["dismissed"], it["dismissedBy"] = True, by
                    return True
            return False
