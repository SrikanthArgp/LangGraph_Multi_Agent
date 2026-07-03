# Auth Flow — Request → DB/Redis → Response

Status as of this writing: `auth/`, `db/`, and `cache/` (Phases 2–4 of `plan.md`) are
built and unit/integration tested **standalone** (see `completed.md`). The
`api/routers/auth.py` FastAPI routes that call these modules over HTTP don't exist
yet — that's Phase 6. Boxes labeled "FastAPI Route" below are the planned Phase 6
handlers; every other box is real, working code today.

## Layers

```mermaid
flowchart TD
    %%{init: {'theme': 'dark'}}%%
    C([Client]) --> R["FastAPI Routes<br>api/routers/auth.py — Phase 6"]
    R --> D["auth/dependencies.py<br>get_current_user"]
    R --> PW["auth/password.py"]
    R --> J["auth/jwt.py"]
    D --> J
    R --> CA[("Redis<br>cache/sessions.py")]
    D --> CA
    R --> PG[("Postgres<br>db/models")]
    D --> PG
```

Why revocation is split across two stores (Redis for access tokens, Postgres for
refresh tokens): access-token checks happen on *every* request and only need to
live 15 minutes, so Redis's speed and auto-expiry fit. Refresh-token revocation
is checked rarely (only at `/auth/refresh`) but must survive a Redis restart
since it's the credential of record, so it lives in Postgres.

---

## 1. Register

```mermaid
flowchart LR
    %%{init: {'theme': 'dark'}}%%
    C([Client]) -- "1 POST /auth/register<br>{email, username, password}" --> RT[FastAPI Route]
    RT -- "2 SELECT WHERE email/username" --> PG[(Postgres<br>users)]
    PG -- "3 no match" --> RT
    RT -- "4 hash_password()" --> PW[auth/password.py]
    PW -- "5 bcrypt hash" --> RT
    RT -- "6 INSERT user" --> PG
    RT -- "7 create_access/refresh_token()" --> J[auth/jwt.py]
    J -- "8 access + refresh JWT" --> RT
    RT -- "9 INSERT refresh_token<br>(sha256 hash)" --> PG
    RT -- "10 201 {tokens, user}" --> C
```

---

## 2. Login

```mermaid
flowchart LR
    %%{init: {'theme': 'dark'}}%%
    C([Client]) -- "1 POST /auth/login<br>{email, password}" --> RT[FastAPI Route]
    RT -- "2 SELECT * WHERE email" --> PG[(Postgres<br>users)]
    PG -- "3 user row" --> RT
    RT -- "4 verify_password()" --> PW[auth/password.py]
    PW -- "5 True/False" --> RT
    RT -- "6 create_access/refresh_token()" --> J[auth/jwt.py]
    J -- "7 access + refresh JWT" --> RT
    RT -- "8 INSERT refresh_token" --> PG
    RT -- "9 200 {access, refresh, ...}" --> C
    RT -. "wrong password / inactive / not found → 401" .-> C
```

---

## 3. Protected request — `GET /auth/me`, any `/sessions/*`

This is `Depends(get_current_user)`, run before the actual route body for every
protected endpoint. **Fully built and tested today**
(`tests/phase3_auth/test_dependencies.py`).

```mermaid
flowchart LR
    %%{init: {'theme': 'dark'}}%%
    C([Client]) -- "1 Bearer access_token" --> RT[FastAPI Route]
    RT -- "2 Depends()" --> D["auth/dependencies.py<br>get_current_user"]
    D -- "3 decode_token()" --> J[auth/jwt.py]
    J -- "4 claims<br>{sub, jti, type, exp}" --> D
    D -- "5 EXISTS revoked_token:jti" --> CA[(Redis)]
    CA -- "6 0 / 1" --> D
    D -- "7 SELECT * WHERE id=sub" --> PG[(Postgres<br>users)]
    PG -- "8 user row" --> D
    D -- "9 user object" --> RT
    RT -- "10 200 response" --> C
    D -. "bad sig / expired / revoked / inactive → 401" .-> C
```

Signature/expiry (step 3–4) is checked before touching Redis or Postgres — a
malformed or expired JWT never costs a network round trip.

---

## 4. Refresh

```mermaid
flowchart LR
    %%{init: {'theme': 'dark'}}%%
    C([Client]) -- "1 POST /auth/refresh<br>{refresh_token}" --> RT[FastAPI Route]
    RT -- "2 decode_token()" --> J[auth/jwt.py]
    J -- "3 claims" --> RT
    RT -- "4 SELECT WHERE token_hash=sha256(...)" --> PG[(Postgres<br>refresh_tokens)]
    PG -- "5 row: revoked?, expired?" --> RT
    RT -- "6 UPDATE ... revoked=True" --> PG
    RT -- "7 SET revoked_token:old_jti EX ttl" --> CA[(Redis)]
    RT -- "8 create_access/refresh_token()" --> J
    J -- "9 new access + refresh JWT" --> RT
    RT -- "10 INSERT new refresh_token" --> PG
    RT -- "11 200 {new tokens}" --> C
    RT -. "invalid / revoked / expired → 401" .-> C
```

Step 6 rotates the refresh token — the old one is marked revoked so it can
never be replayed even if intercepted.

---

## 5. Logout

```mermaid
flowchart LR
    %%{init: {'theme': 'dark'}}%%
    C([Client]) -- "1 Bearer access_token<br>+ optional {refresh_token}" --> RT[FastAPI Route]
    RT -- "2 SET revoked_token:access_jti<br>EX remaining_ttl NX" --> CA[(Redis)]
    RT -- "3 (if refresh_token given)<br>UPDATE refresh_tokens SET revoked=True" --> PG[(Postgres<br>refresh_tokens)]
    RT -- "4 SET revoked_token:refresh_jti EX ttl" --> CA
    RT -- "5 204 No Content" --> C
```

TTL on each Redis key = that token's own remaining lifetime — the blacklist
entry expires itself right when the token would've expired anyway, so it never
needs manual cleanup.

---

## Store responsibilities at a glance

| Concern | Store | Why |
|---|---|---|
| User identity, password hash | Postgres (`users`) | Durable, source of truth |
| Refresh token validity | Postgres (`refresh_tokens`) | Long-lived (7d), must survive Redis restart, needed for reuse-detection |
| Access token blacklist | Redis (`revoked_token:{jti}`) | Checked on every request — needs to be fast; TTL = remaining token life, so it never needs manual cleanup |
| Access/refresh token *contents* | Nowhere — stateless JWT | Signature + `exp` claim is self-validating; only revocation needs a lookup |
