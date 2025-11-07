import json
import asyncio
from typing import Dict
from datetime import datetime, timezone


from fastapi.responses import JSONResponse
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException

from models import Subscriber, Topic
from schemas import CreateTopicRequest
from utilities import make_event, make_error, make_ack, make_pong, make_info

app = FastAPI(title="In-memory Pub/Sub")

# Global registry
TOPICS: Dict[str, Topic] = {}
TOPICS_LOCK = asyncio.Lock()

# Stats
START_TS = datetime.now(timezone.utc)

# -------------- Utilities --------------
async def get_topic(name: str) -> Topic:
    async with TOPICS_LOCK:
        t = TOPICS.get(name)
        if t is None:
            raise KeyError(name)
        return t

async def create_topic(name: str) -> Topic:
    async with TOPICS_LOCK:
        if name in TOPICS:
            raise KeyError("exists")
        t = Topic(name)
        TOPICS[name] = t
        return t

async def delete_topic(name: str):
    async with TOPICS_LOCK:
        t = TOPICS.pop(name, None)
    if t is None:
        raise KeyError("notfound")
    # notify subscribers and close them
    async with t.lock:
        subscribers = list(t.subscribers.values())
        t.subscribers.clear()
    info = make_info(name, "topic_deleted")
    for sub in subscribers:
        try:
            await sub.queue.put(info)
        except asyncio.QueueFull:
            pass
        # we don't forcefully close websockets here; their sender task will notice and exit

# -------------- WebSocket handling --------------
async def subscriber_sender_loop(sub: Subscriber):
    """
    Background task per subscriber: read from queue and send over websocket.
    """
    websocket = sub.websocket
    client_id = sub.client_id
    try:
        while sub.connected:
            item = await sub.queue.get()
            # item should already be serializable dict
            try:
                await websocket.send_text(json.dumps(item))
            except Exception:
                # (broken pipe / closed) -> stop
                break
    except asyncio.CancelledError:
        # Graceful cancellation
        pass
    finally:
        sub.connected = False

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    # we don't create a global client mapping; subscribers are per-topic
    # But we keep a set of topics this ws has subscribed to, for cleanup
    subscribed_topics = set()
    client_websocket_tasks = []
    try:
        while True:
            data = await ws.receive_text()
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                await ws.send_text(json.dumps(make_error(None, "BAD_REQUEST", "invalid json")))
                continue
            # parse minimal fields
            typ = payload.get("type")
            request_id = payload.get("request_id")
            # ping
            if typ == "ping":
                await ws.send_text(json.dumps(make_pong(request_id)))
                continue

            if typ == "subscribe":
                topic_name = payload.get("topic")
                client_id = payload.get("client_id")
                last_n = int(payload.get("last_n") or 0)
                if not topic_name or not client_id:
                    await ws.send_text(json.dumps(make_error(request_id, "BAD_REQUEST", "topic and client_id required")))
                    continue
                # get topic
                try:
                    topic = await get_topic(topic_name)
                except KeyError:
                    await ws.send_text(json.dumps(make_error(request_id, "TOPIC_NOT_FOUND", f"topic {topic_name} not found", topic_name)))
                    continue
                # register subscriber
                async with topic.lock:
                    if client_id in topic.subscribers:
                        # already subscribed; reassign websocket
                        old = topic.subscribers[client_id]
                        await old.stop()
                    sub = Subscriber(client_id, ws)
                    topic.subscribers[client_id] = sub
                # start sender loop
                sub.sender_task = asyncio.create_task(subscriber_sender_loop(sub))
                subscribed_topics.add((topic_name, client_id))
                # send last_n replay
                if last_n > 0:
                    async with topic.lock:
                        history = list(topic.history)[-last_n:]
                    for hist_msg in history:
                        await sub.queue.put(make_event(topic_name, hist_msg))
                await ws.send_text(json.dumps(make_ack(request_id, topic_name)))
                continue

            if typ == "unsubscribe":
                topic_name = payload.get("topic")
                client_id = payload.get("client_id")
                if not topic_name or not client_id:
                    await ws.send_text(json.dumps(make_error(request_id, "BAD_REQUEST", "topic and client_id required")))
                    continue
                try:
                    topic = await get_topic(topic_name)
                except KeyError:
                    await ws.send_text(json.dumps(make_error(request_id, "TOPIC_NOT_FOUND", f"topic {topic_name} not found", topic_name)))
                    continue
                async with topic.lock:
                    sub = topic.subscribers.pop(client_id, None)
                if sub:
                    await sub.stop()
                    subscribed_topics.discard((topic_name, client_id))
                await ws.send_text(json.dumps(make_ack(request_id, topic_name)))
                continue

            if typ == "publish":
                topic_name = payload.get("topic")
                msg = payload.get("message")
                if not topic_name or not msg:
                    await ws.send_text(json.dumps(make_error(request_id, "BAD_REQUEST", "topic and message required")))
                    continue
                # minimal validation: id present
                if "id" not in msg:
                    await ws.send_text(json.dumps(make_error(request_id, "BAD_REQUEST", "message.id required")))
                    continue
                # check topic exists
                try:
                    topic = await get_topic(topic_name)
                except KeyError:
                    await ws.send_text(json.dumps(make_error(request_id, "TOPIC_NOT_FOUND", f"topic {topic_name} not found", topic_name)))
                    continue
                # publish
                await topic.publish(msg)
                await ws.send_text(json.dumps(make_ack(request_id, topic_name)))
                continue

            # unknown type
            await ws.send_text(json.dumps(make_error(request_id, "BAD_REQUEST", f"unknown type: {typ}")))
    except WebSocketDisconnect:
        # cleanup: stop subscriber tasks for any subscribed topics for this websocket
        pass
    except Exception:
        # Unexpected error; attempt to send internal error before closing
        try:
            await ws.send_text(json.dumps(make_error(None, "INTERNAL", "server error")))
        except Exception:
            pass
    finally:
        # Clean up: remove subscriptions that reference this websocket
        async with TOPICS_LOCK:
            topics = list(TOPICS.values())
        for topic in topics:
            async with topic.lock:
                # find subscribers with same websocket and stop & remove
                remove_ids = [cid for cid, s in topic.subscribers.items() if s.websocket == ws]
                for cid in remove_ids:
                    s = topic.subscribers.pop(cid, None)
                    if s:
                        await s.stop()

# -------------- REST endpoints --------------

@app.post("/topics", status_code=201)
async def rest_create_topic(req: CreateTopicRequest):
    name = req.name
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    try:
        await create_topic(name)
    except KeyError:
        return JSONResponse(status_code=409, content={"status": "conflict", "topic": name})
    return {"status": "created", "topic": name}

@app.delete("/topics/{name}")
async def rest_delete_topic(name: str):
    try:
        await delete_topic(name)
    except KeyError:
        raise HTTPException(status_code=404, detail="not found")
    return {"status": "deleted", "topic": name}

@app.get("/topics")
async def rest_list_topics():
    async with TOPICS_LOCK:
        topics = list(TOPICS.values())
    out = []
    for t in topics:
        async with t.lock:
            out.append({"name": t.name, "subscribers": len(t.subscribers)})
    return {"topics": out}

@app.get("/health")
async def rest_health():
    now = datetime.now(timezone.utc)
    uptime_sec = int((now - START_TS).total_seconds())
    async with TOPICS_LOCK:
        topics_count = len(TOPICS)
        subscribers_count = sum(len(t.subscribers) for t in TOPICS.values())
    return {"uptime_sec": uptime_sec, "topics": topics_count, "subscribers": subscribers_count}

@app.get("/stats")
async def rest_stats():
    async with TOPICS_LOCK:
        topic_items = list(TOPICS.items())
    out = {}
    for name, t in topic_items:
        async with t.lock:
            out[name] = {
                "messages": t.messages_published,
                "subscribers": len(t.subscribers)
            }
    return {"topics": out}
