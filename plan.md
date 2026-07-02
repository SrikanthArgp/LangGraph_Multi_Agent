# Productionization Plan — LangGraph CRAG Multi-Agent App

## Context

The current app is a pure-CLI Corrective RAG (CRAG) multi-agent pipeline built with LangGraph. It has:
- **No HTTP API** — entry point is `main.py` (CLI only)
- **In-memory checkpointer** (`MemorySaver`) — all state lost on restart
- **No users, no auth, no sessions**
- **No persistence** (Chroma vector store is persisted; conversation state is not)

This plan transforms it into a production REST API with:
- JWT authentication
- Per-user conversation sessions
- PostgreSQL for durable conversation history + LangGraph checkpoints
- Redis for fast last-5-session listing per user
- RAGAS + LangSmith-based evaluation testing

---

## New Project Structure

```
Multi-Agent/
├── api/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app factory + lifespan context manager
│   ├── dependencies.py            # Shared deps: db session, redis, graph, current user
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py                # POST /auth/register, /auth/login, /auth/refresh, /auth/logout; GET /auth/me
│   │   ├── sessions.py            # GET/POST/PATCH/DELETE /sessions and /sessions/{id}
│   │   └── chat.py                # POST /sessions/{id}/messages; GET /sessions/{id}/stream (SSE)
│   └── schemas/
│       ├── __init__.py
│       ├── auth.py                # RegisterRequest, LoginRequest, TokenResponse, UserResponse, AuthResponse
│       ├── session.py             # SessionCreate, SessionPatch, SessionResponse
│       └── chat.py                # ChatRequest, MessageResponse, ChatResponse, MessagesListResponse
│
├── db/
│   ├── __init__.py
│   ├── base.py                    # async engine, async_sessionmaker, declarative Base
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py                # User ORM model
│   │   ├── session.py             # ChatSession ORM model
│   │   ├── message.py             # Message ORM model
│   │   └── refresh_token.py       # RefreshToken ORM model
│   └── migrations/
│       ├── env.py                 # Alembic env (async-aware)
│       ├── script.py.mako
│       └── versions/
│           └── 0001_initial_schema.py
│
├── cache/
│   ├── __init__.py
│   ├── client.py                  # Redis async client dependency
│   └── sessions.py                # get/set/invalidate for session ZSET, HASH, LIST, revocation STRING
│
├── auth/
│   ├── __init__.py
│   ├── password.py                # bcrypt hash/verify
│   ├── jwt.py                     # create_access_token, create_refresh_token, decode_token
│   └── dependencies.py            # get_current_user FastAPI dependency
│
├── eval/
│   ├── __init__.py
│   ├── dataset.py                 # 25 static QA pairs + push-to-LangSmith function
│   ├── metrics.py                 # RAGAS metric objects + threshold dict
│   ├── langsmith_eval.py          # create_or_get_dataset, run_target, build_ragas_evaluators
│   └── run_eval.py                # CLI: python -m eval.run_eval [--experiment-name foo]
│
├── chains/                        # UNCHANGED
├── nodes/                         # UNCHANGED
├── consts.py                      # UNCHANGED
├── state.py                       # UNCHANGED
├── ingestion.py                   # UNCHANGED
├── graph.py                       # MODIFIED: add create_app(checkpointer) factory
├── main.py                        # MODIFIED: use create_app(MemorySaver()) for CLI
├── alembic.ini
├── pyproject.toml
├── requirements.txt               # EXTENDED
├── .env                           # EXTENDED
└── .env.example                   # UPDATED
```

---

## PostgreSQL Schema

### Application Tables

> Run these in **Supabase Dashboard → SQL Editor** following `setup/db_setup.md`. Do not use Alembic for the initial schema — run it manually so triggers and indexes are applied exactly as written.

```sql
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- USERS
CREATE TABLE users (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    username        VARCHAR(100) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_users_email ON users(email);

-- Auto-update updated_at on any UPDATE
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER users_set_updated_at
    BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- CHAT SESSIONS
-- id is used directly as LangGraph thread_id (cast to text)
CREATE TABLE chat_sessions (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title           VARCHAR(500),
    is_archived     BOOLEAN      NOT NULL DEFAULT FALSE,
    last_message_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_chat_sessions_user_id       ON chat_sessions(user_id);
CREATE INDEX idx_chat_sessions_user_last_msg ON chat_sessions(user_id, last_message_at DESC NULLS LAST);
CREATE INDEX idx_chat_sessions_active        ON chat_sessions(user_id, is_archived, last_message_at DESC NULLS LAST);

CREATE TRIGGER chat_sessions_set_updated_at
    BEFORE UPDATE ON chat_sessions FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- MESSAGES
CREATE TABLE messages (
    id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID         NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role        VARCHAR(20)  NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content     TEXT         NOT NULL,
    metadata    JSONB,          -- stores: web_search flag, routing decision, node path
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_messages_session_id      ON messages(session_id);
CREATE INDEX idx_messages_session_created ON messages(session_id, created_at ASC);

-- REFRESH TOKENS (for revocation)
CREATE TABLE refresh_tokens (
    id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  VARCHAR(64)  NOT NULL,   -- SHA-256 hex of the raw JWT string
    issued_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ  NOT NULL,
    revoked     BOOLEAN      NOT NULL DEFAULT FALSE,
    revoked_at  TIMESTAMPTZ
);
CREATE INDEX idx_refresh_tokens_user_id    ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_token_hash ON refresh_tokens(token_hash);
CREATE INDEX idx_refresh_tokens_active     ON refresh_tokens(user_id, revoked, expires_at);
```

### LangGraph Checkpoint Tables
Created automatically by `AsyncPostgresSaver.setup()` — **do not create manually**.

```sql
-- For reference only (managed by langgraph-checkpoint-postgres):
checkpoints          (thread_id, checkpoint_ns, checkpoint_id, ...)
checkpoint_blobs     (thread_id, checkpoint_ns, channel, version, blob, ...)
checkpoint_writes    (thread_id, checkpoint_ns, checkpoint_id, task_id, idx, ...)
```

**Alignment rule**: `chat_sessions.id::TEXT` = LangGraph `thread_id`. Ownership is enforced at the session layer before any graph call.

---

## Redis Data Model

> For provisioning steps, key schema verification, and Python client setup, see `setup/redis_setup.md`.

### A — User Session Listing (Sorted Set)
```
Key:     user:{user_id}:sessions
Type:    ZSET
Score:   UNIX timestamp of last_message_at
Member:  session_id (UUID string)
Max:     5 members (enforced after every ZADD with ZREMRANGEBYRANK 0 -6)
TTL:     86400 s (refreshed on read/write)

Write:
  ZADD user:{user_id}:sessions {now_ts} {session_id}
  ZREMRANGEBYRANK user:{user_id}:sessions 0 -6
  EXPIRE user:{user_id}:sessions 86400

Read (GET /sessions):
  ZREVRANGE user:{user_id}:sessions 0 4 WITHSCORES
  → on cache miss, query DB LIMIT 5 ORDER BY last_message_at DESC and repopulate
```

### B — Session Metadata Cache (Hash)
```
Key:     session:{session_id}:meta
Type:    HASH
Fields:  title, user_id, created_at, last_message_at, is_archived ("0"/"1")
TTL:     3600 s (refreshed on read)

Write:   HSET session:{session_id}:meta field value ...
         EXPIRE session:{session_id}:meta 3600
Read:    HGETALL session:{session_id}:meta
```

### C — Recent Messages per Session (List)
```
Key:     session:{session_id}:messages
Type:    LIST (append with RPUSH; newest at tail)
Value:   JSON: {"id":"...", "role":"user|assistant", "content":"...", "created_at":"..."}
Max:     20 entries (LTRIM -20 -1 after each RPUSH)
TTL:     1800 s (refreshed on access)

Write:
  RPUSH session:{session_id}:messages {json_message}
  LTRIM session:{session_id}:messages -20 -1
  EXPIRE session:{session_id}:messages 1800

Read:    LRANGE session:{session_id}:messages 0 -1
         → on cache miss, load from DB LIMIT 20 ORDER BY created_at DESC
```

### D — JWT Revocation (String)
```
Key:     revoked_token:{jti}
Type:    STRING
Value:   "1"
TTL:     Remaining lifetime of the token at logout time

On logout:
  SET revoked_token:{access_jti} 1 EX {exp - now}  NX

On every authenticated request:
  EXISTS revoked_token:{jti}  → 401 if found
```

### Redis Config
- `maxmemory-policy allkeys-lru`
- Recommended cap: 512 MB
- All keys have explicit TTLs; LRU eviction naturally expires stale session caches first.

---

## API Endpoints

```
POST   /auth/register
POST   /auth/login
POST   /auth/refresh
POST   /auth/logout                    (auth required)
GET    /auth/me                        (auth required)

GET    /sessions                       → last 5 sessions (Redis → DB fallback)
POST   /sessions                       → create new session
GET    /sessions/{session_id}
PATCH  /sessions/{session_id}          → rename title
DELETE /sessions/{session_id}          → soft-delete (is_archived=True)

GET    /sessions/{session_id}/messages → paginated history (DB)
POST   /sessions/{session_id}/messages → synchronous invoke
GET    /sessions/{session_id}/stream   → SSE token stream

GET    /health                         → liveness/readiness (public)
```

### Key Schema Types
```python
# Auth
RegisterRequest: email, username, password
LoginRequest:    email, password
TokenResponse:   access_token, refresh_token, token_type, expires_in
AuthResponse:    tokens: TokenResponse, user: UserResponse

# Sessions
SessionCreate:   title (optional)
SessionPatch:    title
SessionResponse: id, user_id, title, is_archived, last_message_at, created_at, updated_at

# Chat
ChatRequest:     question (1–4000 chars)
MessageResponse: id, session_id, role, content, metadata, created_at
ChatResponse:    question_message, answer_message

# SSE events (application/json per event):
{"type": "token",  "token": "..."}
{"type": "done",   "message_id": "..."}
{"type": "error",  "detail": "..."}
```

---

## Auth Flow

### JWT Structure
- **Access token**: HS256, 15-minute TTL. Claims: `sub` (user_id), `email`, `username`, `jti`, `type="access"`, `iat`, `exp`
- **Refresh token**: HS256, 7-day TTL. Claims: `sub`, `jti`, `type="refresh"`, `iat`, `exp`

### Request Validation (every protected endpoint)
1. Extract `Bearer` token from `Authorization` header
2. Decode + verify signature and expiry
3. Confirm `type == "access"`
4. Check `EXISTS revoked_token:{jti}` in Redis → 401 if found
5. Load user from DB → 401 if missing or `is_active=False`

### Refresh
- Decode refresh token → verify `type == "refresh"` + not expired
- SHA-256 hash it → look up in `refresh_tokens` table (must be non-revoked, non-expired)
- Mark old row revoked; add `jti` to Redis revocation
- Issue new access + refresh token pair
- Return `TokenResponse`

### Logout
- Add access token `jti` to Redis revocation (`EX = remaining lifetime`)
- If refresh token provided: mark DB row revoked + add `jti` to Redis

---

## LangGraph Integration

### Refactor `graph.py`
Remove module-level `app = workflow.compile(checkpointer=memory)` and replace with:
```python
def create_app(checkpointer):
    """Compile and return the CRAG graph with the given checkpointer."""
    return workflow.compile(checkpointer=checkpointer)
```
Also remove `app.get_graph().draw_mermaid_png(...)` — crashes in headless API environments.

### Update `main.py` (CLI stays working)
```python
from langgraph.checkpoint.memory import MemorySaver
from graph import create_app
app = create_app(MemorySaver())
```

### `AsyncPostgresSaver` lifecycle in `api/main.py`
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pg_pool = AsyncConnectionPool(
        conninfo=settings.DATABASE_URL_PSYCOPG, min_size=2, max_size=10, open=False
    )
    await app.state.pg_pool.open()
    async with AsyncPostgresSaver(app.state.pg_pool) as saver:
        await saver.setup()   # creates checkpoint tables if not exist (idempotent)
    app.state.db_engine = create_async_engine(settings.DATABASE_URL)
    app.state.redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    yield
    await app.state.pg_pool.close()
    await app.state.db_engine.dispose()
    await app.state.redis.aclose()
```

`get_graph` dependency creates `AsyncPostgresSaver(request.app.state.pg_pool)` per request (cheap — pool is the singleton).

### Inline the LangChain Hub prompt (`chains/generation.py`)
`hub.pull("rlm/rag-prompt")` makes a live network call at import time. Replace with:
```python
from langchain_core.prompts import ChatPromptTemplate
prompt = ChatPromptTemplate.from_messages([
    ("human", """You are an assistant for question-answering tasks.
Use the following pieces of retrieved context to answer the question.
If you don't know the answer, say that you don't know. Use three sentences maximum.

Question: {question}
Context: {context}
Answer:""")
])
```

---

## Evaluation Testing

### Dataset (`eval/dataset.py`)
25 static QA pairs drawn from the three ingested Lilian Weng blog posts:
- 20 questions routed to `vectorstore` (agents, prompt engineering, adversarial attacks) — with `ground_truth`
- 5 questions that must route to `websearch` (topics not in corpus) — `ground_truth=None`

### RAGAS Metrics (`eval/metrics.py`)
| Metric | Measures | Needs ground_truth |
|---|---|---|
| `faithfulness` | Answer grounded in retrieved contexts (hallucination detection) | No |
| `answer_relevancy` | Answer addresses the question | No |
| `context_recall` | Retrieved contexts contain the info needed | Yes |
| `context_precision` | Relevant contexts ranked first | Yes |

Default thresholds:
```python
THRESHOLDS = {
    "faithfulness": 0.75,
    "answer_relevancy": 0.75,
    "context_recall": 0.65,
    "context_precision": 0.65,
}
```

### LangSmith Wiring (`eval/langsmith_eval.py`)
- `create_or_get_dataset(name)` — pushes QA pairs to LangSmith (idempotent)
- `run_target(inputs)` — invokes `create_app(MemorySaver())` with a fresh `thread_id` per sample; returns `{answer, contexts}`
- `build_ragas_evaluators()` — wraps RAGAS metrics as LangSmith-compatible evaluators via `ragas.integrations.langsmith`

### Eval Runner (`eval/run_eval.py`)
```bash
python -m eval.run_eval
python -m eval.run_eval --experiment-name prod-baseline-v1
```
- Runs all 25 samples through LangSmith `evaluate()`
- Prints per-metric markdown table with Pass/Fail vs thresholds
- Exits with code `1` if any metric falls below threshold (enables CI gating)
- Prints the LangSmith experiment URL

---

## New Environment Variables

```bash
# PostgreSQL — Supabase (two formats required by different libraries)
# Get these from: Supabase Dashboard → Settings → Database → Connection string
DATABASE_URL=postgresql+psycopg://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
DATABASE_URL_PSYCOPG=host=aws-0-<region>.pooler.supabase.com dbname=postgres user=postgres.<project-ref> password=<password> port=5432
DATABASE_POOL_MIN_SIZE=2
DATABASE_POOL_MAX_SIZE=10

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT — generate with: python -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET_KEY=<64-char hex>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# App
APP_ENV=production
APP_HOST=0.0.0.0
APP_PORT=8000
CORS_ORIGINS=http://localhost:3000

# Existing (unchanged)
OPENAI_API_KEY=sk-...
TAVILY_API_KEY=tvly-...
LANGCHAIN_API_KEY=ls__...
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=crag-production

# Evaluation
LANGSMITH_EVAL_DATASET_NAME=crag-eval-v1
LANGSMITH_EVAL_PROJECT=crag-evals
EVAL_FAITHFULNESS_THRESHOLD=0.75
EVAL_ANSWER_RELEVANCY_THRESHOLD=0.75
EVAL_CONTEXT_RECALL_THRESHOLD=0.65
EVAL_CONTEXT_PRECISION_THRESHOLD=0.65
```

---

## New Packages to Install

```
fastapi==0.115.*
uvicorn[standard]==0.32.*
psycopg[binary]==3.2.*
psycopg-pool==3.2.*
langgraph-checkpoint-postgres==2.0.*
redis==5.2.*
python-jose[cryptography]==3.3.*
passlib[bcrypt]==1.7.*
alembic==1.14.*
ragas==0.2.*
pytest-asyncio==0.24.*
httpx==0.27.*
fakeredis==2.26.*
```

---

## Step-by-Step Migration Order

### Phase 1 — Infrastructure (Day 1)
1. Install new packages; extend `requirements.txt`
2. Provision PostgreSQL via **Supabase**: follow `setup/db_setup.md` step-by-step (create project → run SQL blocks in SQL Editor → copy connection strings to `.env`)
3. Provision Redis (local or managed): follow `setup/redis_setup.md` step-by-step (choose Docker or WSL2 → verify connection → add `REDIS_URL` to `.env`)
4. Extend `.env` with all new variables (Section above)
5. Create `pyproject.toml` with pytest config:
   ```toml
   [tool.pytest.ini_options]
   asyncio_mode = "auto"
   markers = ["integration: marks tests that call real LLMs"]
   ```

### Phase 2 — Database Layer (Day 1–2)
1. Create `db/base.py` — async engine, `async_sessionmaker`, declarative `Base`
2. Create ORM models: `User`, `ChatSession`, `Message`, `RefreshToken` using SQLAlchemy 2.x `mapped_column` syntax
3. `alembic init db/migrations` → configure `alembic.ini` and `db/migrations/env.py` with async engine
4. `alembic revision --autogenerate -m "initial_schema"` → manually add triggers and indexes not captured by autogenerate
5. Skip `alembic upgrade head` for initial setup — tables were already created in Supabase via `setup/db_setup.md`. Use Alembic only for **future schema changes** going forward.

### Phase 3 — Auth Layer (Day 2)
1. `auth/password.py`: `passlib.context.CryptContext(schemes=["bcrypt"], deprecated="auto")`
2. `auth/jwt.py`: `python-jose` encode/decode; `create_access_token`, `create_refresh_token`, `decode_token`
3. `auth/dependencies.py`: `get_current_user` async dep (validates Bearer → revocation check → DB user load)
4. Unit tests for auth (mocked DB + Redis; no LLM calls)

### Phase 4 — Cache Layer (Day 2)
1. `cache/client.py`: `get_redis(request)` dependency from `request.app.state.redis`
2. `cache/sessions.py`: implement all cache helper functions for ZSET/HASH/LIST/STRING patterns
3. Unit tests using `fakeredis.aioredis.FakeRedis`

### Phase 5 — Graph Refactoring (Day 3)
1. Modify `graph.py`: extract `create_app(checkpointer)` factory; remove module-level compile and `draw_mermaid_png`
2. Modify `main.py`: instantiate `MemorySaver()` locally; call `create_app()`
3. Inline LangChain Hub prompt in `chains/generation.py`
4. Verify: `python main.py` and `pytest chains/tests/ -m integration` both pass

### Phase 6 — FastAPI Application (Day 3–5)
1. `api/schemas/` — all Pydantic models
2. `api/dependencies.py` — `get_db`, `get_redis`, `get_graph`, re-export `get_current_user`
3. `api/routers/auth.py` — register, login, refresh, logout, me
4. `api/routers/sessions.py` — CRUD with Redis-first read, DB fallback
5. `api/routers/chat.py` — sync invoke + SSE stream; persist messages; update Redis caches
6. `api/main.py` — lifespan, include routers, CORS, request-ID middleware
7. Manual API smoke test:
   ```bash
   uvicorn api.main:app --reload
   curl -X POST http://localhost:8000/auth/register -H "Content-Type: application/json" \
        -d '{"email":"a@b.com","username":"alice","password":"test1234"}'
   ```
8. Integration tests using `httpx.AsyncClient` against a `crag_test` database

### Phase 7 — Evaluation Suite (Day 5–6)
1. Build 25-sample dataset in `eval/dataset.py` (derive ground_truth from Chroma or blog posts)
2. `eval/metrics.py`: instantiate RAGAS metrics + thresholds dict
3. `eval/langsmith_eval.py`: `create_or_get_dataset`, `run_target`, `build_ragas_evaluators`
4. `eval/run_eval.py`: argparse CLI with threshold gate + markdown output
5. Run baseline: `python -m eval.run_eval --experiment-name baseline-v1`
6. Record baseline scores and LangSmith URL — these become regression thresholds for CI

### Phase 8 — Test Hardening (Day 6)
1. Add `chains/tests/conftest.py` with fixtures for DB, Redis, HTTP client, authenticated user
2. Mark existing 7 tests with `@pytest.mark.integration`
3. Add fast unit tests (no LLM): auth logic, cache logic, ownership validation
4. Verify two-tier test runs:
   ```bash
   pytest -m "not integration"   # fast, no LLM
   pytest -m integration         # slow, requires API keys
   ```

### Phase 9 — Production Hardening (Day 7, optional)
1. Structured logging (`structlog`): include `request_id`, `user_id`, `session_id` in every log line
2. `Dockerfile` (python:3.12-slim, uvicorn CMD)
3. `docker-compose.yml` with `app` and `redis:7` services only — Postgres is provided by Supabase, no local container needed
4. Rate limiting middleware (Redis INCR per user per minute bucket; reject at 60 req/min)
5. `/health` endpoint with real `SELECT 1` DB check and Redis `PING`

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| `chat_sessions.id` = LangGraph `thread_id` | Single UUID serves both layers; no mapping table needed |
| `AsyncPostgresSaver` per request | Thin wrapper; connection pool is the singleton on `app.state` |
| SHA-256 hash refresh tokens in DB | DB row cannot be used to replay the token if DB is leaked |
| SSE over WebSockets | Unidirectional stream, simpler, HTTP/1.1 compatible, auto-reconnects |
| Keep sync nodes (no async conversion) | LangGraph `ainvoke` handles `run_in_executor` automatically; refactor risk not worth it |
| `ZREMRANGEBYRANK 0 -6` for 5-session eviction | Keeps 5 highest-scored (most recent) members atomically |
| Inline LangChain Hub prompt | Eliminates live network call at every import/cold start |
