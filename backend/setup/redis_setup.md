# Redis Setup

Redis is used as the caching layer for this application. It handles four distinct data patterns:

| Pattern | Key | Type | Purpose |
|---------|-----|------|---------|
| A | `user:{user_id}:sessions` | ZSET | Last 5 sessions per user, ordered by recency |
| B | `session:{session_id}:meta` | HASH | Session metadata (title, timestamps, archived flag) |
| C | `session:{session_id}:messages` | LIST | Last 20 messages per session |
| D | `revoked_token:{jti}` | STRING | JWT access token revocation |

All keys carry explicit TTLs. An `allkeys-lru` eviction policy is required — stale session caches are evicted automatically when memory pressure is high.

---

## Step 1 — Choose Your Redis Deployment

> **Pick exactly one option.** Docker and WSL2 both run Redis on `localhost:6379` — running both at the same time will cause a port conflict. If you already have WSL2 with Ubuntu, use Option B and skip Option A entirely.

### Option A — Docker (Recommended if you do not have WSL2)

Docker is the fastest way to run Redis locally on Windows without touching WSL or installing Redis natively.

**Prerequisites:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running.

> **Windows note:** The `\` line-continuation below is bash syntax. Run this command in **Git Bash** or a **WSL2 terminal** — not in PowerShell (which uses backtick `` ` `` for continuation). Alternatively, paste it as a single line in PowerShell.

```bash
docker run -d \
  --name crag-redis \
  --restart unless-stopped \
  -p 6379:6379 \
  -v crag-redis-data:/data \
  redis:7-alpine \
  redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru --appendonly yes
```

**PowerShell equivalent (single line):**
```powershell
docker run -d --name crag-redis --restart unless-stopped -p 6379:6379 -v crag-redis-data:/data redis:7-alpine redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru --appendonly yes
```

Verify it is running:

```bash
docker ps | grep crag-redis
```

Expected output (abbreviated):
```
abc123...   redis:7-alpine   "docker-entrypoint.s…"   Up X seconds   0.0.0.0:6379->6379/tcp   crag-redis
```

To stop and start the container later:
```bash
docker stop crag-redis
docker start crag-redis
```

---

### Option B — WSL2 (Ubuntu)

If you already have WSL2 with Ubuntu, you can install Redis directly.

```bash
sudo apt update
sudo apt install redis-server -y
```

Open the Redis config file:
```bash
sudo nano /etc/redis/redis.conf
```

Find and update these lines (search with `Ctrl+W`):

```
maxmemory 512mb
maxmemory-policy allkeys-lru
appendonly yes
```

Save (`Ctrl+O`, `Enter`) and exit (`Ctrl+X`), then start Redis:

```bash
sudo service redis-server start
```

Check status:
```bash
sudo service redis-server status
```

Expected output:
```
* redis-server is running
```

> **Note:** You will need to run `sudo service redis-server start` each time you start a new WSL session, or enable it to start automatically:
> ```bash
> sudo systemctl enable redis-server
> ```

#### Accessing WSL2 Redis from Windows and VS Code

WSL2 automatically forwards its ports to Windows `localhost`. Redis running inside WSL2 on port `6379` is immediately reachable from Windows, VS Code, and your Python code **without any extra configuration**.

**Verify from Windows (PowerShell or CMD):**
```powershell
Test-NetConnection -ComputerName localhost -Port 6379
```

Expected output:
```
TcpTestSucceeded : True
```

Or, if you have `redis-cli` installed on Windows (e.g., via the Redis MSI or Chocolatey):
```powershell
redis-cli -h localhost -p 6379 PING
# PONG
```

**Your `.env` stays the same regardless of where Redis runs:**
```bash
REDIS_URL=redis://localhost:6379/0
```

This works from both the Windows side and inside WSL2 — `localhost` resolves correctly in both environments.

#### VS Code — Redis GUI in the Editor

Install the **Database Client** extension by Weijan Chen:

1. Open VS Code → Extensions (`Ctrl+Shift+X`)
2. Search for `Database Client` (publisher: **cweijan**)
3. Click **Install**

Connect to Redis:

1. Click the new **Database** icon in the VS Code sidebar (cylinder icon)
2. Click **+** → **Redis**
3. Fill in:
   - **Host:** `localhost`
   - **Port:** `6379`
   - **Password:** *(leave blank for local Redis)*
4. Click **Connect**

You will see all keys in a tree view. You can browse, inspect, and delete keys directly — useful for verifying that the application is writing the correct key patterns during development.

#### Alternative — RedisInsight (Standalone GUI)

[RedisInsight](https://redis.io/insight/) is the official Redis desktop GUI (free). It provides a richer interface than the VS Code extension, including a built-in CLI, memory profiler, and slow log viewer.

1. Download and install RedisInsight from [redis.io/insight](https://redis.io/insight/)
2. Open it → **Add Redis Database**
3. Enter `localhost` and port `6379`
4. Click **Add Redis Database**

RedisInsight connects to the WSL2 Redis instance over `localhost` the same way VS Code does.

---

### Option C — Managed Redis (Production / Cloud)

For production deployments, use a hosted Redis service so you do not manage infrastructure.

**Recommended providers:**

| Provider | Free tier | Notes |
|----------|-----------|-------|
| [Upstash](https://upstash.com) | Yes (10K commands/day) | Serverless, per-request billing, good for low traffic |
| [Redis Cloud](https://redis.io/cloud/) | Yes (30 MB) | Official Redis provider, fixed instance |
| [Railway](https://railway.app) | Yes (limited) | Simple one-click deploy |

After provisioning, you will receive a connection URL in one of these formats:

```bash
# Upstash
redis://default:<password>@<host>.upstash.io:6379

# Redis Cloud / Railway
redis://:<password>@<host>:<port>
```

Copy this URL — you will use it in Step 5 as `REDIS_URL`.

> **Note:** Managed providers handle `maxmemory` and eviction policy settings through their dashboards. Set `maxmemory-policy` to `allkeys-lru` in your provider's configuration panel.

---

## Step 2 — Verify the Connection

Open a Redis CLI shell to confirm Redis is reachable.

**Docker:**
```bash
docker exec -it crag-redis redis-cli
```

**WSL2:**
```bash
redis-cli
```

**Managed (from your machine):**
```bash
redis-cli -u redis://:<password>@<host>:<port>
```

Once inside the CLI, run a `PING`:

```
127.0.0.1:6379> PING
PONG
```

Then check the server configuration:

```
127.0.0.1:6379> CONFIG GET maxmemory
1) "maxmemory"
2) "536870912"

127.0.0.1:6379> CONFIG GET maxmemory-policy
1) "maxmemory-policy"
2) "allkeys-lru"
```

> `536870912` bytes = 512 MB. If you are using a managed provider and cannot run `CONFIG GET`, skip this check — it is enforced by the provider's settings.

Type `exit` or press `Ctrl+C` to leave the CLI.

---

## Step 3 — Understand the Key Schema

This section documents every key pattern the application uses. You do not need to create these manually — the application code writes them at runtime. This is a reference for debugging and monitoring.

### A — User Session Listing

```
Key:    user:{user_id}:sessions
Type:   Sorted Set (ZSET)
Score:  UNIX timestamp of last_message_at
Member: session_id (UUID string)
Max:    5 members (enforced with ZREMRANGEBYRANK 0 -6 on every write)
TTL:    86400 seconds (24 hours, refreshed on read and write)
```

Used by `GET /sessions` to return the 5 most recently active sessions without a database query. On cache miss, the endpoint falls back to PostgreSQL and repopulates this key.

Write pattern:
```redis
ZADD user:{user_id}:sessions {unix_ts} {session_id}
ZREMRANGEBYRANK user:{user_id}:sessions 0 -6
EXPIRE user:{user_id}:sessions 86400
```

Read pattern:
```redis
ZREVRANGE user:{user_id}:sessions 0 4 WITHSCORES
```

---

### B — Session Metadata Cache

```
Key:    session:{session_id}:meta
Type:   Hash (HASH)
Fields: title, user_id, created_at, last_message_at, is_archived ("0" or "1")
TTL:    3600 seconds (1 hour, refreshed on read)
```

Caches metadata for a single session. Used by `GET /sessions/{session_id}` to avoid a roundtrip to PostgreSQL.

Write pattern:
```redis
HSET session:{session_id}:meta title "My session" user_id "..." created_at "..." last_message_at "..." is_archived "0"
EXPIRE session:{session_id}:meta 3600
```

Read pattern:
```redis
HGETALL session:{session_id}:meta
```

---

### C — Recent Messages per Session

```
Key:    session:{session_id}:messages
Type:   List (LIST)
Value:  JSON string: {"id":"...", "role":"user|assistant", "content":"...", "created_at":"..."}
Max:    20 entries (LTRIM -20 -1 after each RPUSH)
TTL:    1800 seconds (30 minutes, refreshed on read and write)
```

Stores the last 20 messages for a session. Used by the chat endpoint to build the context window for the LLM without querying the database on every message.

Write pattern:
```redis
RPUSH session:{session_id}:messages '{"id":"...","role":"user","content":"...","created_at":"..."}'
LTRIM session:{session_id}:messages -20 -1
EXPIRE session:{session_id}:messages 1800
```

Read pattern:
```redis
LRANGE session:{session_id}:messages 0 -1
```

---

### D — JWT Access Token Revocation

```
Key:   revoked_token:{jti}
Type:  String (STRING)
Value: "1"
TTL:   Remaining lifetime of the token at logout time (computed as exp - now)
```

Used to implement stateless JWT revocation. When a user logs out, their access token's `jti` (JWT ID) is written here. Every authenticated request checks `EXISTS revoked_token:{jti}` — a `1` result means the token is revoked and the request is rejected with a `401`.

The TTL is set to the exact remaining lifetime of the token, so the key expires automatically when the token would have expired anyway — no garbage collection needed.

Write pattern (on logout):
```redis
SET revoked_token:{jti} 1 EX {exp - now} NX
```

Check pattern (on every authenticated request):
```redis
EXISTS revoked_token:{jti}
```

---

## Step 4 — Manually Verify Key Patterns (Optional)

You can manually insert and inspect test keys to verify Redis is working correctly before running the application.

Open the Redis CLI (see Step 2), then run:

```redis
# Test ZSET — session listing
ZADD user:test-user-001:sessions 1700000000 "session-aaa"
ZADD user:test-user-001:sessions 1700000100 "session-bbb"
ZADD user:test-user-001:sessions 1700000200 "session-ccc"
EXPIRE user:test-user-001:sessions 86400
ZREVRANGE user:test-user-001:sessions 0 4 WITHSCORES
```

Expected output:
```
1) "session-ccc"
2) "1700000200"
3) "session-bbb"
4) "1700000100"
5) "session-aaa"
6) "1700000000"
```

```redis
# Test HASH — session metadata
HSET session:session-aaa:meta title "Test session" user_id "test-user-001" is_archived "0"
EXPIRE session:session-aaa:meta 3600
HGETALL session:session-aaa:meta
```

Expected output:
```
1) "title"
2) "Test session"
3) "user_id"
4) "test-user-001"
5) "is_archived"
6) "0"
```

```redis
# Test LIST — recent messages
RPUSH session:session-aaa:messages '{"id":"msg-001","role":"user","content":"What is an LLM agent?","created_at":"2024-01-01T10:00:00Z"}'
RPUSH session:session-aaa:messages '{"id":"msg-002","role":"assistant","content":"An LLM agent is...","created_at":"2024-01-01T10:00:05Z"}'
LTRIM session:session-aaa:messages -20 -1
EXPIRE session:session-aaa:messages 1800
LRANGE session:session-aaa:messages 0 -1
```

Expected output:
```
1) "{\"id\":\"msg-001\",\"role\":\"user\",\"content\":\"What is an LLM agent?\",\"created_at\":\"2024-01-01T10:00:00Z\"}"
2) "{\"id\":\"msg-002\",\"role\":\"assistant\",\"content\":\"An LLM agent is...\",\"created_at\":\"2024-01-01T10:00:05Z\"}"
```

```redis
# Test STRING — token revocation
SET revoked_token:test-jti-001 1 EX 900 NX
EXISTS revoked_token:test-jti-001
TTL revoked_token:test-jti-001
```

Expected output:
```
OK
(integer) 1
(integer) 900      ← approximate; will be slightly less due to command latency
```

Clean up test keys:
```redis
DEL user:test-user-001:sessions
DEL session:session-aaa:meta
DEL session:session-aaa:messages
DEL revoked_token:test-jti-001
```

---

## Step 5 — Add `REDIS_URL` to Your `.env`

Add the following line to your `.env` file:

**Local (Docker or WSL2):**
```bash
REDIS_URL=redis://localhost:6379/0
```

**Managed provider (replace with your actual URL):**
```bash
REDIS_URL=redis://:<password>@<host>:<port>/0
```

The `/0` at the end selects database index 0 (the default). Redis supports 16 databases (0–15); using index 0 is conventional for the primary application.

> **Note:** Never commit your `.env` file. Keep `.env.example` up to date with placeholder values for every variable so other developers know what is required — see the full list of variables in `.env.example` at the root of this project.

---

## Step 6 — Install the Python Redis Client

The application uses `redis-py` with `redis.asyncio` for async operations. Install it with:

```bash
pip install "redis==5.2.*"
```

For unit tests, install `fakeredis` — it provides an in-memory Redis implementation that requires no running server:

```bash
pip install "fakeredis==2.26.*"
```

Both packages will be listed in `pyproject.toml` / `requirements.txt` after Phase 1 of the migration plan.

---

## Step 7 — Smoke Test the Python Connection

Create a quick test script to confirm the Python client can reach Redis:

```python
# test_redis_connection.py
import asyncio
import redis.asyncio as aioredis

async def main():
    client = aioredis.from_url("redis://localhost:6379/0", decode_responses=True)
    pong = await client.ping()
    print(f"PING → {pong}")           # PING → True
    await client.set("smoke_test", "ok", ex=10)
    val = await client.get("smoke_test")
    print(f"GET smoke_test → {val}")  # GET smoke_test → ok
    await client.delete("smoke_test")
    await client.aclose()

asyncio.run(main())
```

Run it:
```bash
python test_redis_connection.py
```

Expected output:
```
PING → True
GET smoke_test → ok
```

Delete the script when done — it is not part of the application.

---

## Summary

| Step | What it does |
|------|-------------|
| 1 | Provision Redis — Docker (local, pick one) or WSL2 (local, pick one) or managed (production) |
| 2 | Verify connectivity with `redis-cli PING` and check `maxmemory` config |
| 3 | Understand the four key patterns: ZSET, HASH, LIST, STRING |
| 4 | Optionally insert test keys to confirm each type works correctly |
| 5 | Add `REDIS_URL` to `.env` |
| 6 | Install `redis==5.2.*` (runtime) and `fakeredis==2.26.*` (tests) |
| 7 | Run the Python smoke test to confirm async client connectivity |

---

## Related Setup

- **PostgreSQL / Supabase** — see [`setup/db_setup.md`](db_setup.md) for the full database provisioning steps including connection strings, table creation, and RLS policies.
