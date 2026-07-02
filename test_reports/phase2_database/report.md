# Phase 2 — Database Layer Test Report

**Reports on:** `tests/phase2_database/`
**Last run:** 2026-07-02
**Command:** `pytest tests/phase2_database/ -v`
**Environment:** Live Supabase Postgres (`ap-southeast-1`), SQLAlchemy 2.x async ORM, Alembic (async template)
**Result:** 20 / 20 passed

---

## `test_models.py` — 11 tests
*Pure metadata assertions — no database connection needed, checks the ORM model definitions themselves.*

| Test | Functionality Verified | Result |
|---|---|---|
| `test_all_tables_registered_on_base_metadata` | All four ORM models (`User`, `ChatSession`, `Message`, `RefreshToken`) are registered and discoverable together. | ✅ Pass |
| `test_users_table_columns` | The `User` model has the right columns, with `email` and `username` enforced unique and `hashed_password`/`is_active` required. | ✅ Pass |
| `test_users_email_index_present` | The `User` model declares the `idx_users_email` lookup index. | ✅ Pass |
| `test_chat_sessions_columns_and_foreign_key` | The `ChatSession` model has the right columns, and `user_id` is a foreign key to `users` that cascades on delete. | ✅ Pass |
| `test_chat_sessions_indexes_present` | All 3 `ChatSession` indexes (user lookup, recency ordering, active-session filtering) are declared. | ✅ Pass |
| `test_messages_role_check_constraint` | The `Message` model restricts the `role` column to `user`/`assistant`/`system` — bad data can't be written even by mistake. | ✅ Pass |
| `test_messages_metadata_attr_maps_to_metadata_column` | The Python attribute `metadata_` (renamed because `metadata` is reserved by SQLAlchemy) correctly maps to the real `metadata` database column. | ✅ Pass |
| `test_messages_foreign_key_cascades_on_delete` | `Message.session_id` is a foreign key to `chat_sessions` that cascades on delete. | ✅ Pass |
| `test_refresh_tokens_columns_and_foreign_key` | The `RefreshToken` model has the right columns, and `user_id` is a foreign key to `users` that cascades on delete. | ✅ Pass |
| `test_refresh_tokens_indexes_present` | All 3 `RefreshToken` indexes are declared. | ✅ Pass |
| `test_relationships_wired_both_directions` | Every ORM relationship (`User↔ChatSession`, `ChatSession↔Message`, `User↔RefreshToken`) is wired in both directions, so navigating from either side works. | ✅ Pass |

## `test_migrations.py` — 3 tests
*Checks the ORM/Alembic setup against the real live database.*

| Test | Functionality Verified | Result |
|---|---|---|
| `test_orm_models_match_live_schema` | The ORM models produce **zero** schema drift against the live database — if a model is ever changed without a matching migration, this test catches it. | ✅ Pass |
| `test_alembic_history_has_single_head` | The migration history has exactly one head — no branching or conflicting migrations. | ✅ Pass |
| `test_live_db_stamped_at_latest_head` | The live database's recorded migration version matches the latest migration in the codebase. | ✅ Pass |

## `test_crud.py` — 6 tests
*Real INSERT/DELETE against the live Supabase database, each wrapped in a savepoint that is always rolled back — proves actual read/write behavior, not just schema shape, without leaving test data behind.*

| Test | Functionality Verified | Result |
|---|---|---|
| `test_create_user_generates_id_and_defaults` | Creating a user through the ORM gets a real generated ID and correct default values (timestamps, active flag) straight from the database. | ✅ Pass |
| `test_duplicate_email_violates_unique_constraint` | Trying to create two users with the same email is rejected — email uniqueness is enforced for real, not just in the model. | ✅ Pass |
| `test_chat_session_relationship_round_trip` | A chat session created for a user is correctly retrievable through that user's `sessions` relationship. | ✅ Pass |
| `test_message_role_check_constraint_rejects_invalid_role` | Trying to save a message with an invalid role (e.g. not user/assistant/system) is rejected by the database. | ✅ Pass |
| `test_message_metadata_jsonb_round_trip` | Arbitrary structured data (e.g. routing decisions) written to a message's metadata is stored and read back correctly. | ✅ Pass |
| `test_deleting_user_cascades_to_sessions_and_refresh_tokens` | Deleting a user automatically removes all of their chat sessions and refresh tokens — no orphaned data left behind. | ✅ Pass |

---

**Notes:**
- All Phase 2 tests skip (not fail) if `DATABASE_URL` isn't set.
- `test_crud.py` writes to the **live shared dev database** but always rolls back via a SAVEPOINT — verified independently (queried `users` for leftover rows after a full run: zero). This pattern will be replaced by a dedicated test database in Phase 8.
- Encountered and fixed a Windows-specific bug during this phase: psycopg's async driver can't run on Python's default `ProactorEventLoop` on Windows. Fixed once in `tests/conftest.py` (and separately in `db/migrations/env.py` for Alembic) — see `completed.md` for detail.
