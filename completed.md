# Progress Log — CRAG Multi-Agent Productionization

Tracks progress against `plan.md`. Update this file as phases complete so a new
session can pick up without re-deriving context.

---

## Done

### Local environment (pre-Phase 1)
- Created `.venv` (Python 3.11.13) and installed deps via `uv sync`.
- Fixed `pyproject.toml`:
  - Added missing `langchain-chroma` and `beautifulsoup4` (used by `ingestion.py` but undeclared).
  - Added `[tool.uv] package = false` — this is a flat script project, not an installable package (hatchling build was failing).
  - Pinned `langchain`/`langgraph`/`chromadb`/etc. to the pre-1.0 API this codebase targets (`langchain>=0.3,<0.4`, `langgraph>=0.2,<0.3`, ...). Unpinned ranges resolved to breaking 1.x releases.
- Fixed `graph.py`: `load_dotenv()` was called *after* importing chain modules that instantiate `ChatOpenAI()` at import time — API key wasn't loaded yet. Moved `load_dotenv()` to the top of the file.
- Fixed `nodes/web_search.py`: `state["documents"]` raised `KeyError` when the router sends a question straight to `websearch` (skipping `retrieve`), since `documents` was never set in state. Changed to `state.get("documents")`.
- Verified `python ingestion.py` and `python main.py` run end-to-end (including the direct-to-websearch path).
- Committed and pushed to remote **`github`** (`SearchAssistantProduction.git`), commit `859e1d8`.
  - Note: remote **`origin`** (`LangGraph_Multi_Agent.git`) is a separate remote, still 2 commits behind — not pushed there yet (user's call, not yet decided).

### Phase 1 — Infrastructure
- **PostgreSQL (Supabase)**: project created, region `ap-southeast-1`.
  - Ran full schema from `setup/db_setup.md`: `pgcrypto` extension, `users`, `chat_sessions`, `messages`, `refresh_tokens` tables with all indexes and the `set_updated_at` trigger (on `users` and `chat_sessions`).
  - Verified via direct `psycopg` connection: all 4 tables, both triggers, all indexes present as expected.
  - RLS intentionally left **disabled** — backend connects as the `postgres` role directly (bypasses RLS regardless), no Supabase-client-direct access path exists yet. Production RLS policy stubs are documented in `setup/db_setup.md` Step 13 for when that changes.
  - `.env` populated with `DATABASE_URL` (transaction pooler, port 6543, `+psycopg` driver, `sslmode=require`) and `DATABASE_URL_PSYCOPG` (session pooler, port 5432, `sslmode=require`) — both URL-encoded for special characters in the password.
  - **Security note**: the original DB password was accidentally echoed unmasked into the chat transcript once; it was rotated immediately after via Supabase dashboard before continuing. Current password in `.env` is the rotated one.
  - LangGraph checkpoint tables (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`) are **not created yet** — they auto-create on first `AsyncPostgresSaver.setup()` call, which happens in Phase 5/6 (not built yet).
- **Redis (Docker)**: container `crag-redis` running (`redis:7-alpine`), `--restart unless-stopped`, port 6379, volume `crag-redis-data`, `maxmemory 512mb`, `maxmemory-policy allkeys-lru`, `appendonly yes`.
  - Verified `PING`, `CONFIG GET maxmemory` (536870912), `CONFIG GET maxmemory-policy` (`allkeys-lru`).
  - `.env` populated with `REDIS_URL=redis://localhost:6379/0`.
  - Async Python smoke test (`redis.asyncio`) confirmed working.
  - `redis` and `fakeredis` already present via `pyproject.toml` `prod`/`dev` extras — installed via `uv sync --extra dev --extra prod`.

**Phase 1 status: complete.** Both Postgres and Redis are provisioned, reachable, and credentials are in `.env` (gitignored, not committed).

### Phase 2 — Database Layer
- `db/base.py`: async engine via `create_async_engine(DATABASE_URL)` (psycopg3 async dialect), pool sized from `DATABASE_POOL_MIN_SIZE`/`MAX_SIZE`, `pool_pre_ping=True`; `async_session_factory` (`async_sessionmaker`); declarative `Base`.
- ORM models (`db/models/{user,session,message,refresh_token}.py`) using SQLAlchemy 2.x `mapped_column` — columns, FKs (`ondelete="CASCADE"`), indexes, and the `messages.metadata` JSONB column (mapped to Python attribute `metadata_` since `metadata` is reserved by `DeclarativeBase`) all verified to match the live Supabase schema **exactly** (`alembic revision --autogenerate` produced an empty diff against the live DB).
- Alembic wired with the **async template** (`alembic init -t async db/migrations`), `db/migrations/env.py` loads `DATABASE_URL` from `.env` (with `%` escaped for configparser interpolation — Supabase passwords contain `%`) and sets `target_metadata = Base.metadata`.
  - **Windows gotcha**: psycopg's async mode cannot run on the default `ProactorEventLoop`. `env.py`'s `run_migrations_online()` now sets `asyncio.WindowsSelectorEventLoopPolicy()` on `sys.platform == "win32"` before `asyncio.run(...)`. This will matter again in Phase 6 (FastAPI/uvicorn) if running on Windows.
  - Revision `a7f571ea1f94_initial_schema.py` is **hand-written** (not left as the empty autogenerate diff) to fully reproduce `setup/db_setup.md`'s SQL — `pgcrypto`, all 4 tables, all 9 indexes, the `set_updated_at()` function, and both triggers — so it's replayable against a fresh DB (e.g. the Phase 8 CI test DB) via `alembic upgrade head`.
  - The **live Supabase DB was stamped, not upgraded**: `alembic stamp head` (not `alembic upgrade head`), per plan.md — tables already exist from the manual SQL setup. Verified via `alembic current` → `a7f571ea1f94 (head)`.
- Tests added in `tests/phase2_database/`: `test_models.py` (pure metadata/relationship assertions, no DB needed), `test_migrations.py` (`requires_db`: live-schema-vs-model diff via `alembic.autogenerate.compare_metadata`, single-head check, stamped-version check), and `test_crud.py` (`requires_db`: real INSERT/DELETE against live Supabase inside a per-test SAVEPOINT that's always rolled back — covers ID/timestamp defaults, unique-email constraint, FK relationship round-trip, the `role` CHECK constraint, `metadata` JSONB round-trip, and cascade delete User → ChatSession/RefreshToken). Verified zero leftover rows in `users` after the run. 31 Phase 1 + Phase 2 tests pass together.
- `pg_conn` and `pg_sync_engine` fixtures promoted from `tests/phase1_infrastructure/conftest.py` to root `tests/conftest.py` since Phase 2 needed `pg_conn` too — avoids duplicating the skip-if-missing fixture logic.
- The Windows `ProactorEventLoop` issue hit a second time — pytest-asyncio itself defaults to Proactor on Windows, breaking `db_session`'s async engine connect. Fixed once at the root: `tests/conftest.py` now sets `asyncio.WindowsSelectorEventLoopPolicy()` at import time (mirrors the `db/migrations/env.py` fix), so it applies to every async test in the suite, not just Alembic.
- `tests/phase2_database/conftest.py`: `db_session` fixture binds an `AsyncSession` to a connection with `join_transaction_mode="create_savepoint"`, always rolled back in a `finally` — the pattern to reuse for any future test that needs to write to the shared dev DB without leaving data behind (relevant again once Phase 6 API integration tests need real writes, before the Phase 8 dedicated test DB exists).

**Phase 2 status: complete.**

### Phase 3 — Auth Layer
- **Deviation from plan.md**: dropped `passlib[bcrypt]`, hash with the `bcrypt` package directly. `passlib` 1.7.4 (unmaintained since 2020) is incompatible with `bcrypt>=4.0` (removed `__about__.__version__`, and bcrypt 5.x raises instead of silently truncating on passlib's internal 72-byte self-test — confirmed by actually running it, not just reading changelogs). Pinning `bcrypt<4.0` isn't viable either: `chromadb` (already a dependency) requires `bcrypt>=4.0.1`, so the two constraints are unresolvable together. `auth/password.py` now uses `bcrypt.hashpw`/`bcrypt.checkpw` directly, truncating input to 72 bytes explicitly (bcrypt's own documented limit) on both hash and verify so round-trips stay consistent. `pyproject.toml` updated: `passlib[bcrypt]>=1.7` → `bcrypt>=4.0`, with a comment explaining why.
- `auth/jwt.py`: `create_access_token` (15 min TTL; claims `sub`/`email`/`username`/`jti`/`type=access`/`iat`/`exp`), `create_refresh_token` (7 day TTL; `sub`/`jti`/`type=refresh`), `decode_token` — all via `python-jose`, HS256, reading `JWT_SECRET_KEY`/`JWT_ALGORITHM`/`ACCESS_TOKEN_EXPIRE_MINUTES`/`REFRESH_TOKEN_EXPIRE_DAYS` from the environment.
- `auth/dependencies.py`: `get_current_user` — a real FastAPI dependency (`Depends(HTTPBearer())` → decode → confirm `type=access` → check `EXISTS revoked_token:{jti}` in Redis → load user from DB → reject if missing/inactive), all raising `HTTPException(401)`. Also defines `get_db_session` (yields from `db.base.async_session_factory`) and `get_redis_client` (creates a connection per call from `REDIS_URL`) as its own default `Depends` providers, since `api/dependencies.py` (Phase 6) and `cache/client.py` (Phase 4) don't exist yet — plan.md's Phase 6 note that `api/dependencies.py` "re-exports `get_current_user`" implies this dependency is meant to be self-contained now and have its providers overridden later via `app.dependency_overrides`, not rebuilt.
- `.env` populated with `JWT_SECRET_KEY` (generated via `secrets.token_hex(32)`), `JWT_ALGORITHM=HS256`, `ACCESS_TOKEN_EXPIRE_MINUTES=15`, `REFRESH_TOKEN_EXPIRE_DAYS=7`.
- Tests in `tests/phase3_auth/`: `test_password.py` (4 — round trip, wrong password, salting, >72-byte truncation), `test_jwt.py` (5 — claims shape, tampered signature, expired token, wrong secret), `test_dependencies.py` (5 — valid token, revoked jti, refresh-token-as-access rejected, unknown user, inactive user) using `fakeredis` and a hand-rolled fake DB session — no real DB/Redis/LLM calls needed. 14/14 pass.
- Full-suite regression check after the bcrypt swap: 51/52 passed across `tests/` + `chains/tests/`. The 1 failure (`test_hallucination_grader_answer_no`) is a pre-existing LLM-judgment flake unrelated to this phase (not touched).

**Phase 3 status: complete.**

### Phase 4 — Cache Layer
- `cache/client.py`: `get_redis(request)` — pulls the singleton `redis.asyncio.Redis` from `request.app.state.redis` (set up in Phase 6's lifespan). Trivial by design; `cache/sessions.py` functions take a redis client as a plain parameter instead of resolving it themselves, so they're testable without any FastAPI machinery.
- `cache/sessions.py`: all 4 key patterns from `setup/redis_setup.md`, matching the write/read semantics documented there exactly (TTL refreshed on both read and write for the ZSET and LIST patterns; TTL set on write and refreshed on read for the HASH pattern; TTL fixed at creation — never refreshed — for the revocation STRING, since extending it would defeat the point):
  - `add_session_to_listing` / `get_recent_sessions` — ZSET, keeps only the 5 most recent sessions per user (`ZREMRANGEBYRANK`), 24h TTL.
  - `set_session_meta` / `get_session_meta` — HASH, 1h TTL.
  - `push_message` / `get_recent_messages` — LIST, keeps only the last 20 messages (`LTRIM`), JSON-serialized, 30min TTL.
  - `revoke_token` / `is_token_revoked` — STRING with `NX`, TTL = remaining token lifetime.
  - All writes use a Redis pipeline (`transaction=True`) so the write + trim + expire happen atomically.
- Tests, two layers (both exercise the exact same `cache/sessions.py` functions):
  - `tests/phase4_cache/test_sessions.py` — 8 tests against `fakeredis.aioredis.FakeRedis`, fast/offline, matches `plan.md`'s spec.
  - `tests/phase4_cache/test_sessions_real_redis.py` — 4 tests (`requires_redis`) against the **real Docker `crag-redis` container** (user has Docker Desktop + WSL2, offered to use it) — proves `fakeredis` isn't hiding real-world discrepancies. Each test cleans up its own keys; verified independently afterward with `docker exec crag-redis redis-cli KEYS '*'` → empty.
  - `redis_async_client` fixture added to root `tests/conftest.py` (function-scoped, not session-scoped — an async redis client bound to one test's event loop breaks in the next test under pytest-asyncio's per-function loop scope). Distinct from the pre-existing sync `redis_client` fixture in `tests/phase1_infrastructure/conftest.py`, which stays as-is for the raw health checks.
- 12/12 new tests pass. Full regression across Phases 1-4: 57/57.

**Phase 4 status: complete.**

### Decision (2026-07-02) — Langfuse for agent observability, replacing LangSmith
User requested Langfuse for agent observability. Clarified two forks with the user before writing anything: **Langfuse Cloud** (not self-hosted) and **replacing** LangSmith entirely (not running both). This was a **docs-only** pass — `plan.md`, `.env.example`, and `CLAUDE.md` were updated; no code was written (that starts at Phase 5, per the plan itself — see below).
- **Why replace LangSmith, not add alongside it**: `plan.md` already had LangSmith wired into two places — `LANGCHAIN_TRACING_V2`/`LANGCHAIN_API_KEY` for general tracing, and `eval/langsmith_eval.py` for the Phase 7 RAGAS eval suite (`create_or_get_dataset`, `run_target`, `build_ragas_evaluators` via `ragas.integrations.langsmith`). Both roles map directly onto Langfuse (`langfuse.langchain.CallbackHandler` for tracing; `create_dataset`/`create_dataset_item`/`item.get_langchain_handler()`/`generation.score()` for eval), so keeping both would just double-instrument every LLM call for no benefit.
- `plan.md` changes: new `## Observability (Langfuse)` section (after "LangGraph Integration") with the actual current integration pattern — verified against live Langfuse docs (via context7), not recalled from training data, since the SDK changed significantly between v2 and v3. Current pattern is `from langfuse.langchain import CallbackHandler; CallbackHandler()` (reads `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`/`LANGFUSE_HOST` from env), passed via `config={"callbacks": [handler]}` on graph `.invoke()`/`.stream()`. Also: added a `observability/langfuse_client.py` module to the project structure tree; reworked the Phase 7 Evaluation Testing section to use Langfuse's dataset/scoring API instead of LangSmith's; renamed `eval/langsmith_eval.py` → `eval/langfuse_eval.py` everywhere; swapped `LANGCHAIN_*`/`LANGSMITH_*` env vars for `LANGFUSE_*` in "New Environment Variables"; added `langfuse==3.*` to "New Packages to Install"; added a new **Phase 10 — Observability (Langfuse)** section — numbered last only so it has a phase slot consistent with `tests/phaseN_*/`/`test_reports/phaseN_*/` naming, but its note is explicit that the actual wiring happens in **Phase 5, step 4** (as soon as `create_app()` exists), not deferred to the end.
- While already editing "New Packages to Install" for this, also fixed a stale line unrelated to Langfuse: it still listed `passlib[bcrypt]==1.7.*`, contradicting the Phase 3 deviation already recorded above. Changed to `bcrypt>=4.0` with a pointer to the Phase 3 note.
- `.env.example` changes: `LANGCHAIN_API_KEY`/`LANGCHAIN_TRACING_V2`/`LANGCHAIN_PROJECT` → `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`/`LANGFUSE_HOST`; `LANGSMITH_EVAL_DATASET_NAME`/`LANGSMITH_EVAL_PROJECT` → `LANGFUSE_EVAL_DATASET_NAME` (the RAGAS `EVAL_*_THRESHOLD` vars are provider-agnostic, left unchanged).
- `CLAUDE.md` changes: fixed the Setup section's tracing-vars line to match; **also added a new "Productionization Migration (in progress)" section**, since `CLAUDE.md` previously didn't mention `plan.md`/`completed.md`/`test_reports/` existed at all — a real gap for any future session that only reads `CLAUDE.md` and not the full conversation history.
- Real `.env` was **not** updated with `LANGFUSE_*` values — no Langfuse account/keys provided yet. That's the first thing Phase 5 step 4 needs before the callback handler can actually be tested.

---

## Not Done Yet — Next Steps

Continue with **Phase 5 — Graph Refactoring** from `plan.md`:
- Modify `graph.py`: extract `create_app(checkpointer)` factory; remove module-level compile and `draw_mermaid_png`
- Modify `main.py`: instantiate `MemorySaver()` locally; call `create_app()`
- Inline the LangChain Hub prompt in `chains/generation.py` (drops a live network call at import time)
- **New**: `observability/langfuse_client.py` (`get_langfuse_handler()`), wired into `main.py`'s `app.stream(...)` call — needs real `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` in `.env` first (get from a Langfuse Cloud account — not yet created)
- Verify: `python main.py` and `pytest chains/tests/ -m integration` both still pass, and the run shows up in the Langfuse dashboard

After Phase 5, remaining phases in order (see `plan.md` for full detail):
- **Phase 6** — FastAPI application (schemas, routers, `api/main.py` lifespan, manual smoke test)
- **Phase 7** — Evaluation suite (RAGAS + Langfuse, 25-sample dataset)
- **Phase 8** — Test hardening (fixtures, unit vs. integration test split)
- **Phase 9** — Production hardening (optional: structured logging, Docker, rate limiting, `/health`)
- **Phase 10** — Observability (Langfuse) — mostly a bookkeeping phase; the real wiring already happens in Phase 5/6/7 above, per the plan's own note

---

## Environment Reference (no secrets)

- `.venv` created with `uv`, Python 3.11.13. Install/update deps: `uv sync --extra dev --extra prod --extra eval`.
- `.env` currently has: `OPENAI_API_KEY`, `TAVILY_API_KEY`, `DATABASE_URL`, `DATABASE_URL_PSYCOPG`, `DATABASE_POOL_MIN_SIZE`, `DATABASE_POOL_MAX_SIZE`, `REDIS_URL`, `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`.
- Still missing from `.env`: `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`/`LANGFUSE_HOST` (needed starting Phase 5 step 4 — no Langfuse account created yet), the `APP_*`/`CORS_ORIGINS` vars (Phase 6), plus `LANGFUSE_EVAL_DATASET_NAME`/eval threshold vars (Phase 7) — see `plan.md` "New Environment Variables" section for the full list.
- `passlib` is **not** used for password hashing despite `plan.md` originally specifying it — see the Phase 3 note above. `auth/password.py` uses `bcrypt` directly. (`plan.md` itself has since been corrected to match.)
- **Langfuse, not LangSmith**, is the observability/eval tool going forward — see the Decision note above. Nothing in `.env` or code reflects this yet; only `plan.md`/`.env.example`/`CLAUDE.md` do.
- Redis container lifecycle: `docker stop crag-redis` / `docker start crag-redis` (data persists in the `crag-redis-data` volume).
