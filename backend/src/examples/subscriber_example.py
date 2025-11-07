import asyncio
import json
import uuid
import websockets

async def main():
    uri = "ws://localhost:8000/ws"
    async with websockets.connect(uri) as ws:
        sub = {
            "type": "subscribe",
            "topic": "orders",
            "client_id": "s1",
            "last_n": 5,
            "request_id": str(uuid.uuid4())
        }
        await ws.send(json.dumps(sub))
        # read ack and then wait for events
        print("Awaiting messages... (press Ctrl+C to exit)")
        try:
            while True:
                msg = await ws.recv()
                print("Received:", msg)
        except KeyboardInterrupt:
            unsub = {"type": "unsubscribe", "topic": "orders", "client_id": "s1", "request_id": str(uuid.uuid4())}
            await ws.send(json.dumps(unsub))
            print("Unsubscribed.")

if __name__ == "__main__":
    asyncio.run(main())