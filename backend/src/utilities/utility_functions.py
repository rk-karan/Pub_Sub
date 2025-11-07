from collections import deque
from datetime import datetime, timezone
from typing import Optional

def now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()

# Server -> client messages are built as dicts
def make_ack(request_id: Optional[str], topic: Optional[str], status: str = "ok"):
    return {"type": "ack", "request_id": request_id, "topic": topic, "status": status, "ts": now_ts()}

def make_pong(request_id: Optional[str]):
    return {"type": "pong", "request_id": request_id, "ts": now_ts()}

def make_event(topic: str, message: dict):
    return {"type": "event", "topic": topic, "message": message, "ts": now_ts()}

def make_error(request_id: Optional[str], code: str, message: str, topic: Optional[str] = None):
    return {"type": "error", "request_id": request_id, "topic": topic, "error": {"code": code, "message": message}, "ts": now_ts()}

def make_info(topic: Optional[str], msg: str):
    return {"type": "info", "topic": topic, "msg": msg, "ts": now_ts()}