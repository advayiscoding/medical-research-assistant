#!/usr/bin/env bash
# Apply DB migrations, then launch the API. Migrations are idempotent (Alembic
# no-ops if already at head), so restarts are safe. We wait for Postgres first
# because compose's depends_on only orders start, not readiness.
set -euo pipefail

echo "Waiting for Postgres…"
until python -c "
import asyncio, asyncpg, os, sys
url = os.environ['DATABASE_URL'].replace('+asyncpg', '')
async def check():
    conn = await asyncpg.connect(url)
    await conn.close()
try:
    asyncio.run(check())
except Exception as e:
    sys.exit(1)
" 2>/dev/null; do
  sleep 1
done

echo "Running migrations…"
alembic upgrade head

echo "Starting API…"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
