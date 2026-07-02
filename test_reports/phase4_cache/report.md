# Phase 4 — Cache Layer Test Report

**Reports on:** `tests/phase4_cache/`
**Last run:** 2026-07-02
**Command:** `pytest tests/phase4_cache/ -v`
**Environment:** `test_sessions.py` uses `fakeredis` (in-memory, no external dependency). `test_sessions_real_redis.py` uses the real Docker `crag-redis` container (`redis://localhost:6379/0`).
**Result:** 12 / 12 passed

---

## `test_sessions.py` — 8 tests (fast, `fakeredis`)

| Test | Functionality Verified | Result |
|---|---|---|
| `test_add_session_to_listing_keeps_only_5_most_recent` | Adding a 6th session to a user's session listing evicts the oldest one — only the 5 most recent sessions are ever kept. | ✅ Pass |
| `test_get_recent_sessions_refreshes_ttl` | Reading a user's session listing refreshes its expiry, so actively-used listings don't expire out from under a user. | ✅ Pass |
| `test_session_meta_round_trip` | A session's cached metadata (title, archived flag, etc.) can be written and read back correctly. | ✅ Pass |
| `test_session_meta_has_ttl_after_write` | Writing session metadata sets an expiry on it immediately, rather than leaving it cached forever. | ✅ Pass |
| `test_push_message_trims_to_20_most_recent` | Pushing a 21st+ message to a session's cache automatically drops the oldest ones — only the last 20 messages are ever kept, in the correct order. | ✅ Pass |
| `test_get_recent_messages_round_trips_json` | A structured message (id/role/content) written to the cache is read back as the exact same structure, not corrupted or flattened. | ✅ Pass |
| `test_revoke_token_then_is_token_revoked_true` | Revoking a token makes it show up as revoked immediately afterward, with an expiry matching the token's own remaining lifetime. | ✅ Pass |
| `test_revoke_token_with_non_positive_ttl_is_a_no_op` | Trying to revoke a token that's already expired (zero or negative remaining lifetime) is safely ignored instead of erroring or writing a broken cache entry. | ✅ Pass |

## `test_sessions_real_redis.py` — 4 tests (`requires_redis`, real Docker container)
*Same functions as above, run against the actual Redis instance instead of an in-memory fake — proves the fake isn't hiding a real-world discrepancy.*

| Test | Functionality Verified | Result |
|---|---|---|
| `test_add_and_get_recent_sessions_against_real_redis` | The session-listing pattern works against real Redis, not just the in-memory fake. | ✅ Pass |
| `test_session_meta_round_trip_against_real_redis` | The session-metadata pattern works against real Redis. | ✅ Pass |
| `test_push_and_get_messages_against_real_redis` | The message-list pattern (including JSON round-trip) works against real Redis. | ✅ Pass |
| `test_revoke_and_check_token_against_real_redis` | The token-revocation pattern works against real Redis. | ✅ Pass |

---

**Notes:**
- Real-Redis tests clean up their own keys after each test; verified independently with `docker exec crag-redis redis-cli KEYS '*'` → empty after the full run.
- All Phase 4 tests skip (not fail) if `REDIS_URL` isn't set.
- Full regression across Phases 1–4 together: 57/57 passed.
