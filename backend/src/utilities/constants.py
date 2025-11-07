# ------------ Config ------------
SUBSCRIBER_QUEUE_SIZE = 50    # bounded per-subscriber queue
REPLAY_BUFFER_SIZE = 100      # last N messages to keep per topic
HEARTBEAT_INTERVAL = 30       # seconds for server-initiated info/ping (optional)
# --------------------------------