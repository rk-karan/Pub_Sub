In-memory Pub/Sub (Python) - Quick Start
========================================

What:
- WebSocket endpoint /ws supports publish, subscribe, unsubscribe, ping.
- REST endpoints:
  POST /topics         { "name": "orders" }
  DELETE /topics/{name}
  GET /topics
  GET /health
  GET /stats

Backpressure policy:
- Each subscriber has a bounded queue (SUBSCRIBER_QUEUE_SIZE, default 50).
- On overflow we drop the oldest message in the subscriber queue, enqueue a SLOW_CONSUMER error message to notify the subscriber, then enqueue the new message.
- This trades strict delivery for availability and prevents a single slow client from blocking publishers.

Replay:
- Each topic keeps the last REPLAY_BUFFER_SIZE messages (default 100).
- Subscribe with "last_n": 5 will replay up to the last 5 messages.

Run locally:
1. Create a topic:
   curl -X POST -H "Content-Type: application/json" -d '{"name":"orders"}' http://localhost:8000/topics

2. Start server:
   cd backend/src
   pip install -r requirements.txt
   uvicorn main:app --host 0.0.0.0 --port 8000

3. Use websocket clients (examples provided) or `wscat`:
   - subscribe with:
     { "type": "subscribe", "topic": "orders", "client_id": "s1", "last_n": 5 }

Docker:
   Make sure you are at the root folder with docker-compose file.
   docker compose up -d

Notes / Assumptions:
- No auth implemented (X-API-Key omitted).
- No persistence across restarts.
- Graceful shutdown tries to stop per-subscriber sender tasks; outstanding messages in memory may be lost on abrupt kill.
- Single-process async server (uvicorn worker=1) — good for the assignment scope. For multi-process you'd need shared state (not allowed by constraint) or external storage.

Files:
- main.py: server
- models.py: models used across the codebase
- schemas.py: schemas used across the codebase
- constants.py: constants used across the codebase
- utility_functions.py: helper functions used across the codebase
- requirements.txt
- Dockerfile
- docker-compose
- publisher_example.py / subscriber_example.py: small clients

