import asyncio
from collections import deque
from typing import Dict, Deque, Optional
from fastapi import WebSocket
from utilities import make_event, make_error 
from utilities import SUBSCRIBER_QUEUE_SIZE, REPLAY_BUFFER_SIZE

# ------------ In-memory structures ------------
class Subscriber:
    def __init__(self, client_id: str, websocket: WebSocket):
        self.client_id = client_id
        self.websocket = websocket
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
        self.sender_task: Optional[asyncio.Task] = None
        self.connected = True

    async def stop(self):
        self.connected = False
        if self.sender_task:
            self.sender_task.cancel()
            try:
                await self.sender_task
            except asyncio.CancelledError:
                pass

class Topic:
    def __init__(self, name: str):
        self.name = name
        self.subscribers: Dict[str, Subscriber] = {}
        self.history: Deque[dict] = deque(maxlen=REPLAY_BUFFER_SIZE)
        self.lock = asyncio.Lock()
        # stats
        self.messages_published = 0

    async def publish(self, msg: dict):
        
        # locking before critical section
        async with self.lock:
            self.history.append(msg)
            self.messages_published += 1
            subscribers = list(self.subscribers.values())
            
        # fan-out outside lock
        for sub in subscribers:
            # try enqueue, if full drop oldest and enqueue SLOW_CONSUMER info for that subscriber
            if sub.queue.full():
                # drop oldest
                try:
                    _ = sub.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                
                # insert a SLOW_CONSUMER error into queue to notify client
                err = make_error(None, "SLOW_CONSUMER", "Subscriber queue overflow; oldest message dropped", self.name)
                try:
                    sub.queue.put_nowait(err)
                except asyncio.QueueFull:
                    # if still full, force put (not ideal, but ensure notification)
                    await sub.queue.put(err)
            # finally put the event
            ev = make_event(self.name, msg)
            try:
                sub.queue.put_nowait(ev)
            except asyncio.QueueFull:
                # shouldn't happen after the drop logic, but fallback: await put
                await sub.queue.put(ev)