# Phase 3 — Auth Layer Test Report

**Reports on:** `tests/phase3_auth/`
**Last run:** 2026-07-02
**Command:** `pytest tests/phase3_auth/ -v`
**Environment:** No live DB/Redis/LLM needed — `fakeredis` in-memory Redis and a hand-rolled fake DB session stand in for the real infrastructure.
**Result:** 14 / 14 passed

---

## `test_password.py` — 4 tests

| Test | Functionality Verified | Result |
|---|---|---|
| `test_hash_and_verify_round_trip` | A password can be hashed and then correctly verified against that hash. | ✅ Pass |
| `test_wrong_password_fails_verification` | An incorrect password is correctly rejected against an existing hash. | ✅ Pass |
| `test_same_password_hashes_differently_each_time` | Hashing the same password twice produces two different hashes (salting is working), and both still verify correctly. | ✅ Pass |
| `test_passwords_longer_than_72_bytes_still_hash_and_verify` | Very long passwords don't crash hashing — they're truncated to bcrypt's 72-byte limit consistently on both hash and verify, so round-trips still work. | ✅ Pass |

## `test_jwt.py` — 5 tests

| Test | Functionality Verified | Result |
|---|---|---|
| `test_access_token_round_trip_has_expected_claims` | An access token carries the right identity claims (user id, email, username) and a valid expiry after the issue time. | ✅ Pass |
| `test_refresh_token_round_trip_has_expected_claims` | A refresh token carries only the minimal claims it needs (no email/username) and has the correct 7-day lifetime. | ✅ Pass |
| `test_tampered_token_is_rejected` | A token whose contents were modified after signing is rejected — the signature check actually works. | ✅ Pass |
| `test_expired_token_is_rejected` | A token past its expiry time is rejected, even though its signature is otherwise valid. | ✅ Pass |
| `test_token_signed_with_wrong_secret_is_rejected` | A token signed with a different secret than the app's is rejected — someone can't forge a valid-looking token without knowing the real secret. | ✅ Pass |

## `test_dependencies.py` — 5 tests
*Exercises `get_current_user`, the dependency every protected API endpoint will use once Phase 6 exists.*

| Test | Functionality Verified | Result |
|---|---|---|
| `test_valid_access_token_returns_active_user` | A valid, non-revoked access token for an active user correctly resolves to that user. | ✅ Pass |
| `test_revoked_token_is_rejected` | A token that's been logged out (its `jti` marked revoked in Redis) is rejected even though the token itself is still cryptographically valid. | ✅ Pass |
| `test_refresh_token_used_as_access_token_is_rejected` | A refresh token can't be used in place of an access token to authenticate a request. | ✅ Pass |
| `test_unknown_user_is_rejected` | A well-formed token for a user that no longer exists in the database is rejected. | ✅ Pass |
| `test_inactive_user_is_rejected` | A well-formed token for a deactivated (`is_active=False`) user is rejected. | ✅ Pass |

---

**Notes:**
- Deviation from `plan.md`: password hashing uses `bcrypt` directly instead of `passlib[bcrypt]`. `passlib` (unmaintained since 2020) is incompatible with `bcrypt>=4.0`, and `chromadb` already requires `bcrypt>=4.0.1` — the two constraints can't be satisfied together. See `completed.md` Phase 3 notes for the full story.
- Full regression check after this change: 51/52 passed across the whole `tests/` + `chains/tests/` suite. The 1 failure is a pre-existing, unrelated LLM-judgment flake in `chains/tests/test_chains.py::test_hallucination_grader_answer_no`.
- These tests never touch a real database, Redis instance, or LLM — they're fast and safe to run on every commit.
