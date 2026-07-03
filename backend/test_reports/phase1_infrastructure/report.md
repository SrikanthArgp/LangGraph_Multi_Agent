# Phase 1 — Infrastructure Test Report

**Reports on:** `tests/phase1_infrastructure/`
**Last run:** 2026-07-02
**Command:** `pytest tests/phase1_infrastructure/ -v`
**Environment:** Live Supabase Postgres (`ap-southeast-1`), local Docker Redis (`crag-redis`), live OpenAI + Tavily APIs, local Chroma store (`.chroma/`)
**Result:** 17 / 17 passed

---

## `test_postgres_health.py` — 5 tests

| Test | Functionality Verified | Result |
|---|---|---|
| `test_select_1` | The app can open a live connection to the Postgres/Supabase instance and execute a query. | ✅ Pass |
| `test_pgcrypto_extension_enabled` | The `pgcrypto` extension is installed — required for `gen_random_uuid()`, which every table uses as its primary key default. | ✅ Pass |
| `test_application_tables_exist` | All four application tables (`users`, `chat_sessions`, `messages`, `refresh_tokens`) exist in the database. | ✅ Pass |
| `test_updated_at_triggers_exist` | The `updated_at` auto-refresh triggers exist on `users` and `chat_sessions`, so edits to those rows automatically stamp the current time. | ✅ Pass |
| `test_indexes_exist` | All 9 performance indexes defined in `setup/db_setup.md` are present on the live database. | ✅ Pass |

## `test_redis_health.py` — 6 tests

| Test | Functionality Verified | Result |
|---|---|---|
| `test_ping` | The app can reach the Redis instance and get a response. | ✅ Pass |
| `test_eviction_policy_is_allkeys_lru` | Redis is configured with the `allkeys-lru` eviction policy, so stale session caches are dropped automatically under memory pressure instead of causing errors. | ✅ Pass |
| `test_zset_session_listing_pattern_roundtrip` | The "last 5 sessions per user" sorted-set pattern can be written, read back in the right (most-recent-first) order, and carries a TTL. | ✅ Pass |
| `test_hash_session_meta_pattern_roundtrip` | The session-metadata hash pattern can be written and read back correctly. | ✅ Pass |
| `test_list_messages_pattern_roundtrip` | The "last 20 messages per session" list pattern can be pushed, trimmed, and read back in order. | ✅ Pass |
| `test_string_revocation_pattern_with_ttl` | The JWT-revocation pattern (a string key set with `NX` and an expiry) is written correctly and carries the expected TTL — this is what makes logout actually invalidate a token. | ✅ Pass |

## `test_chroma_health.py` — 2 tests *(marked `integration` — calls OpenAI embeddings)*

| Test | Functionality Verified | Result |
|---|---|---|
| `test_collection_returns_documents` | The local Chroma vector store is populated and returns relevant results for a real query. | ✅ Pass |
| `test_collection_covers_multiple_source_topics` | The vector store has ingested content from more than one of the three source blog posts, not just one. | ✅ Pass |

## `test_external_services_health.py` — 4 tests *(marked `integration` — real API calls, real cost)*

| Test | Functionality Verified | Result |
|---|---|---|
| `test_openai_key_present` | An OpenAI API key is configured in the environment. | ✅ Pass |
| `test_openai_chat_completion_reachable` | The app can make a real call to OpenAI's chat completion API and get back a response. | ✅ Pass |
| `test_tavily_key_present` | A Tavily API key is configured in the environment. | ✅ Pass |
| `test_tavily_search_reachable` | The app can make a real call to the Tavily search API and get back results. | ✅ Pass |

---

**Notes:**
- Postgres/Redis tests are skipped (not failed) if `DATABASE_URL_PSYCOPG` / `REDIS_URL` aren't set — safe to run without infra provisioned.
- Chroma + external-service tests cost real API calls; run them deliberately (`pytest tests/phase1_infrastructure/ -m "not integration"` to skip them).
