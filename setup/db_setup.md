# Supabase Database Setup

## Step 1 — Create a Supabase Project

1. Go to [https://supabase.com](https://supabase.com) and sign in (or create a free account).
2. Click **New project**.
3. Fill in:
   - **Name**: `crag-multi-agent` (or any name you prefer)
   - **Database Password**: choose a strong password and save it somewhere safe
   - **Region**: pick the one closest to you
4. Click **Create new project** and wait ~2 minutes for it to provision.

---

## Step 2 — Get Your Connection Strings

1. In your project dashboard, go to **Settings → Database**.
2. Scroll to **Connection string** section.
3. Copy both formats and add them to your `.env` file:

```bash
# SQLAlchemy async format (used by FastAPI / SQLAlchemy) — Transaction pooler, port 6543
DATABASE_URL=postgresql+psycopg://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres?sslmode=require

# psycopg DSN format (used by LangGraph AsyncPostgresSaver) — Session pooler, port 5432
DATABASE_URL_PSYCOPG=host=aws-0-<region>.pooler.supabase.com dbname=postgres user=postgres.<project-ref> password=<password> port=5432 sslmode=require
```

> **Note:** Supabase's Supavisor pooler exposes two modes on different ports:
> - **Transaction mode** (port **6543**) — used by `DATABASE_URL` (FastAPI/SQLAlchemy). Efficient for short-lived async requests.
> - **Session mode** (port **5432**) — used by `DATABASE_URL_PSYCOPG` (LangGraph `AsyncPostgresSaver`). Required because `AsyncPostgresSaver` uses psycopg3 prepared statements, which are not supported in transaction pooling mode.
>
> `sslmode=require` is mandatory — Supabase rejects unencrypted connections.

---

## Step 3 — Open the SQL Editor

1. In your Supabase dashboard, click **SQL Editor** in the left sidebar.
2. Click **New query**.
3. You will run each SQL block below one at a time.

---

## Step 4 — Enable pgcrypto Extension

Run this first — it provides `gen_random_uuid()` used by all tables.

```sql
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
```

Click **Run**. You should see `Success. No rows returned`.

---

## Step 5 — Create the `users` Table

```sql
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
```

---

## Step 6 — Create the `set_updated_at` Trigger Function

This function automatically updates the `updated_at` column to the current time whenever a row is updated. Run it once — it is shared by multiple tables.

```sql
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

---

## Step 7 — Attach the Trigger to `users`

```sql
CREATE TRIGGER users_set_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

---

## Step 8 — Create the `chat_sessions` Table

The `id` column of this table is used directly as the LangGraph `thread_id`.

```sql
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
    BEFORE UPDATE ON chat_sessions
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

---

## Step 9 — Create the `messages` Table

```sql
CREATE TABLE messages (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID        NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role        VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content     TEXT        NOT NULL,
    metadata    JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_messages_session_id      ON messages(session_id);
CREATE INDEX idx_messages_session_created ON messages(session_id, created_at ASC);
```

The `metadata` JSONB column stores graph execution details per message: routing decision (`vectorstore` vs `websearch`), whether web search was triggered, and the node path taken.

---

## Step 10 — Create the `refresh_tokens` Table

```sql
CREATE TABLE refresh_tokens (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  VARCHAR(64) NOT NULL,
    issued_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked     BOOLEAN     NOT NULL DEFAULT FALSE,
    revoked_at  TIMESTAMPTZ
);

CREATE INDEX idx_refresh_tokens_user_id    ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_token_hash ON refresh_tokens(token_hash);
CREATE INDEX idx_refresh_tokens_active     ON refresh_tokens(user_id, revoked, expires_at);
```

`token_hash` stores the SHA-256 hex of the raw JWT string — never the token itself.

---

## Step 11 — Verify All Tables

Run these queries to confirm all tables, triggers, and indexes were created successfully.

**Tables:**
```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
```

Expected output:
```
chat_sessions
messages
refresh_tokens
users
```

**Triggers:**
```sql
SELECT trigger_name, event_object_table
FROM information_schema.triggers
WHERE trigger_schema = 'public'
ORDER BY event_object_table;
```

Expected output:
```
chat_sessions_set_updated_at   chat_sessions
users_set_updated_at           users
```

**Indexes:**
```sql
SELECT indexname, tablename
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;
```

Expected output:
```
chat_sessions_pkey                  chat_sessions
idx_chat_sessions_active            chat_sessions
idx_chat_sessions_user_id           chat_sessions
idx_chat_sessions_user_last_msg     chat_sessions
messages_pkey                       messages
idx_messages_session_created        messages
idx_messages_session_id             messages
refresh_tokens_pkey                 refresh_tokens
idx_refresh_tokens_active           refresh_tokens
idx_refresh_tokens_token_hash       refresh_tokens
idx_refresh_tokens_user_id          refresh_tokens
users_pkey                          users
idx_users_email                     users
```

---

## Step 12 — LangGraph Checkpoint Tables (Do NOT create manually)

The three LangGraph checkpoint tables are created automatically when `AsyncPostgresSaver.setup()` runs at app startup:

```
checkpoints
checkpoint_blobs
checkpoint_writes
```

You do not need to do anything here — they will appear in your Supabase **Table Editor** after the first time you start the FastAPI app.

---

## Step 13 — Disable Row Level Security (for development)

Supabase enables RLS on all tables by default. For local development, disable it on your app tables so your backend can read/write without policy setup:

```sql
ALTER TABLE users          DISABLE ROW LEVEL SECURITY;
ALTER TABLE chat_sessions  DISABLE ROW LEVEL SECURITY;
ALTER TABLE messages       DISABLE ROW LEVEL SECURITY;
ALTER TABLE refresh_tokens DISABLE ROW LEVEL SECURITY;
```

> **Note:** Re-enable RLS and add policies before deploying to production. Your backend connects as the `postgres` service role (bypasses RLS by default), so disabling RLS here only affects direct Supabase client access. At minimum, add these policies when hardening for production:
>
> ```sql
> -- Re-enable RLS
> ALTER TABLE users          ENABLE ROW LEVEL SECURITY;
> ALTER TABLE chat_sessions  ENABLE ROW LEVEL SECURITY;
> ALTER TABLE messages       ENABLE ROW LEVEL SECURITY;
> ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY;
>
> -- Users can only read/update their own row
> CREATE POLICY users_self ON users
>     USING (id = auth.uid()::uuid);
>
> -- Users can only access their own sessions
> CREATE POLICY sessions_owner ON chat_sessions
>     USING (user_id = auth.uid()::uuid);
>
> -- Users can only access messages in their own sessions
> CREATE POLICY messages_owner ON messages
>     USING (session_id IN (
>         SELECT id FROM chat_sessions WHERE user_id = auth.uid()::uuid
>     ));
>
> -- Users can only see their own refresh tokens
> CREATE POLICY refresh_tokens_owner ON refresh_tokens
>     USING (user_id = auth.uid()::uuid);
> ```
>
> See [Supabase RLS docs](https://supabase.com/docs/guides/database/postgres/row-level-security) for full policy options.

---

## Step 14 — Update Your `.env` File

Add the following to your `.env` (replace placeholders with values from Step 2):

```bash
# PostgreSQL — Transaction pooler for SQLAlchemy (port 6543)
DATABASE_URL=postgresql+psycopg://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres?sslmode=require
# PostgreSQL — Session pooler for LangGraph AsyncPostgresSaver (port 5432)
DATABASE_URL_PSYCOPG=host=aws-0-<region>.pooler.supabase.com dbname=postgres user=postgres.<project-ref> password=<password> port=5432 sslmode=require
DATABASE_POOL_MIN_SIZE=2
DATABASE_POOL_MAX_SIZE=10

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT — generate secret with: python -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET_KEY=<64-char hex>
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
```

---

## Related Setup

- **Redis cache layer** — see [`setup/redis_setup.md`](redis_setup.md) for Redis provisioning, key schema, and Python client setup.

---

## Summary

| Step | What it creates |
|------|----------------|
| 1–2  | Supabase project + connection strings (Session vs Transaction pooler, `sslmode=require`) |
| 3    | SQL Editor access |
| 4    | `pgcrypto` extension |
| 5–7  | `users` table + `set_updated_at` trigger function |
| 8    | `chat_sessions` table + trigger |
| 9    | `messages` table |
| 10   | `refresh_tokens` table |
| 11   | Verification queries — tables, triggers, and indexes |
| 12   | LangGraph checkpoint tables (auto-created at app startup) |
| 13   | RLS disabled for development + production RLS policy stubs |
| 14   | `.env` updated with DB URLs (correct ports), Redis, and JWT vars |
