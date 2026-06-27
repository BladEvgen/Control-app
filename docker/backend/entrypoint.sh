#!/bin/sh
set -e

echo "[entrypoint] waiting for database (${DB_HOST:-mysql}:${DB_PORT:-3306})..."
python - <<'PYEOF'
import os
import socket
import time

host = os.getenv("DB_HOST", "mysql")
port = int(os.getenv("DB_PORT", "3306"))

for _ in range(60):
    try:
        with socket.create_connection((host, port), timeout=2):
            break
    except OSError:
        time.sleep(2)
else:
    raise SystemExit(f"Database {host}:{port} not reachable")
PYEOF

echo "[entrypoint] ready, starting: $*"
exec "$@"
