# from typing import Any, Optional
from pydantic import BaseModel

# class Message(BaseModel):
#     id: str
#     payload: Any

# class WSIncoming(BaseModel):
#     type: str  # subscribe|unsubscribe|publish|ping
#     topic: Optional[str] = None
#     message: Optional[dict] = None
#     client_id: Optional[str] = None
#     last_n: Optional[int] = 0
#     request_id: Optional[str] = None

class CreateTopicRequest(BaseModel):
    name: str