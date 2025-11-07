import asyncio
import json
import uuid
import websockets  # lightweight client; to install: pip install websockets

async def main():
    uri = "ws://localhost:8000/ws"
    async with websockets.connect(uri) as ws:
        # publish a test message to topic 'orders'
        msg = {
            "type": "publish",
            "topic": "orders",
            "message": {
                "id": str(uuid.uuid4()),
                "payload": {"order_id": "ORD-1", "amount": 9.99, "currency": "USD"}
            },
            "request_id": str(uuid.uuid4())
        }
        print("Client Message: ", msg)
        await ws.send(json.dumps(msg))
        resp = await ws.recv()
        print("Server:", resp)

if __name__ == "__main__":
    asyncio.run(main())