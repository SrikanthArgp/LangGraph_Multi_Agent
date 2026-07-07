# Phase 17 — CI Pipeline: Step-by-Step

Scope: a deliberately minimal GitHub Actions workflow — lint (`ruff`) + the fast unit test tier (`pytest -m "not integration"`) on every push/PR to `main`. No build, no deploy — that's Phases 18/19. Full design/rationale lives in `plan.md`'s Phase 17 section — this doc is the execution checklist plus the operational detail (workflow YAML, gotchas) the plan intentionally left out.

Status: planning only, nothing built yet. Sequenced after both AWS deploy targets (Phase 15 Lambda, Phase 16 ECS) — see `plan.md`'s 2026-07-07 renumbering decision. Companion to [`cd-lambda-deploy-steps.md`](./cd-lambda-deploy-steps.md) and [`cd-ecs-deploy-steps.md`](./cd-ecs-deploy-steps.md), which both trigger after this workflow goes green.

---

## Architecture Overview

```mermaid
flowchart LR
    Dev(["Developer"]) -->|push / PR to main| Trigger["GitHub Actions trigger\non: push, pull_request"]
    Trigger --> Checkout["Checkout code"]
    Checkout --> SetupUV["Install uv\n(astral-sh/setup-uv)"]
    SetupUV --> Sync["uv sync --extra dev --frozen\n(backend/, working-directory)"]
    Sync --> Lint["ruff check ."]
    Lint -->|fail| Blocked1["Workflow fails\nPR shows red X"]
    Lint -->|pass| Test["python -m pytest -m \"not integration\"\n(fast unit tier)"]
    Test -->|fail| Blocked2["Workflow fails\nPR shows red X"]
    Test -->|pass| Green["Status check: success"]
    Green --> Gate{"Required status check\nset in branch protection?"}
    Gate -->|yes| Merge["Merge blocked until green\n(actually enforced)"]
    Gate -->|no| Warn["Green check is advisory only —\nmerge is NOT actually blocked"]
```

The gate at the bottom is deliberately drawn as a decision, not an assumption — creating `ci.yml` makes the check *exist*, it doesn't make the check *required*. See Gotchas.

---

## Why this stays minimal

Every other phase in this plan (15, 16, 18, 19) earns its complexity from a real constraint — SSE streaming, IAM scoping, VPC networking. CI doesn't have an equivalent forcing function yet: there's no deploy stage wired to it (that's Phases 18/19), no matrix of Python versions to support (single target, `>=3.11`), and no frontend job (frontend has its own Vitest/Playwright suites from Phases 7–8, not in scope here — this workflow is backend-only, matching `plan.md`'s framing). Adding coverage reporting, dependency caching tuned beyond the default, or a lint-fix-and-commit step now would be solving problems this project doesn't have yet. Keep it to two jobs-worth of work — lint, test — until something concrete demands more.

---

## Prerequisites

- A GitHub repo with `main` as the default branch (already true).
- Nothing else — unlike Phases 15/16, this workflow needs no AWS credentials, no LocalStack, no secrets at all in its current lint+test-only scope.

---

## Steps

1. Add `ruff` to `backend/pyproject.toml`'s `dev` extra — **it isn't there yet** (verified: `dev = ["pytest>=8.0", "pytest-asyncio>=0.24", "httpx>=0.27", "fakeredis>=2.26"]`, no `ruff` entry as of this writing). Run `uv add --optional dev ruff` from `backend/` and commit the updated `pyproject.toml` + `uv.lock` before writing the workflow, or step 5 below fails on `ruff: command not found`.
2. Decide a ruff config if one doesn't exist yet — a `[tool.ruff]` block in `pyproject.toml` (or a `ruff.toml`). Without one, `ruff check .` runs with ruff's defaults, which is fine to start, but pin a `target-version` matching `requires-python = ">=3.11"` so ruff's rule set doesn't assume a newer syntax baseline than the project supports.
3. Create `.github/workflows/ci.yml` (see the full workflow below).
4. Set `working-directory: backend` (via `defaults.run` at the job level, not per-step) — this repo's convention is that all commands run from `backend/`, not the repo root; see `CLAUDE.md`.
5. Steps inside the job: checkout → install `uv` → `uv sync --extra dev --frozen` → `ruff check .` → `python -m pytest -m "not integration"` (not bare `pytest` — see Gotchas).
6. Verify: push a branch with a deliberate lint error and a deliberate failing test, confirm both fail the workflow; fix both, confirm it goes green.
7. Go to the repo's branch protection settings for `main` and add this workflow's job as a **required status check** — the workflow existing does not do this automatically (see Gotchas).

---

## GitHub Actions Workflow

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

# Cancel superseded runs on the same PR/branch instead of letting them queue —
# a lint+test job is cheap, but there's no reason to run five stale ones back to back.
concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          version: "latest"
          # Caches uv's own download + the resolved venv, keyed on uv.lock —
          # a no-op sync on an unchanged lock file goes from ~20s to ~2s.
          enable-cache: true
          cache-dependency-glob: "backend/uv.lock"

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies (frozen)
        run: uv sync --extra dev --frozen

      - name: Lint
        run: uv run ruff check .

      - name: Fast unit test tier
        run: uv run python -m pytest -m "not integration"
        env:
          # config.py's Settings has four required (no-default) fields; some
          # code paths construct Settings() during app/TestClient startup even
          # in the fast tier, which fails collection without these. Values are
          # dummy — the fast tier never makes a real DB/Redis connection with
          # them. See Gotchas for how to confirm this is actually needed.
          DATABASE_URL: "postgresql+asyncpg://test:test@localhost:5432/test"
          DATABASE_URL_PSYCOPG: "postgresql://test:test@localhost:5432/test"
          REDIS_URL: "redis://localhost:6379/0"
          JWT_SECRET_KEY: "ci-dummy-secret-not-for-real-use"
```

---

## Gotchas

- **`ruff` isn't installed yet.** `backend/pyproject.toml`'s `dev` extra doesn't include it (verified by reading the file directly, not assumed) — `uv sync --extra dev` alone will not make `ruff check .` work. Add it first (step 1 above). This is the single most likely reason a first attempt at this workflow goes red immediately, and it'll look like a CI misconfiguration when it's actually a missing dependency.

- **Bare `pytest` fails in this workflow the same way it fails locally on Windows — for a different, cross-platform reason.** `completed.md`'s Phase 11 entry documents that the bare `pytest` console-script does not add the current working directory to `sys.path` (no `pythonpath` set in `[tool.pytest.ini_options]`, no root `conftest.py`), so `pytest tests/ ... -m "not integration"` fails collection with `ModuleNotFoundError` for first-party imports (`config`, `api`, `multi_agent`, ...). `python -m pytest` does add cwd to `sys.path` and is the form that actually works — and this isn't Windows-specific, it's how Python's `-m` flag behaves everywhere, so `ubuntu-latest` runners hit the exact same failure if the workflow uses bare `pytest`/`uv run pytest`. Use `uv run python -m pytest`, matching `CLAUDE.md`'s own documented local command.

- **`Settings()` may construct eagerly during test collection, not just at real app startup.** `config.py`'s `Settings` has four fields with no default: `database_url`, `database_url_psycopg`, `redis_url`, `jwt_secret_key` — a missing one raises a `pydantic.ValidationError` at construction time. Locally this is masked by `tests/conftest.py`'s `load_dotenv()` reading a real `backend/.env`; CI has no `.env` file at all, and `load_dotenv()` silently no-ops if the file doesn't exist rather than erroring. If any fast-tier test imports something that triggers a `TestClient`/app-lifespan construction (even indirectly, through a shared fixture), it'll fail on missing settings before it fails for any test-logic reason. **Confirm whether this is actually hit** by running `uv run python -m pytest -m "not integration"` locally with `backend/.env` temporarily renamed — if it still passes, the dummy env vars in the workflow above are unnecessary defensive weight and can be dropped; if it fails, they're required, not optional.

- **Registered `pytest` markers avoid a red herring.** `backend/pyproject.toml`'s `[tool.pytest.ini_options]` already registers `integration`, `requires_db`, and `requires_redis` as markers — so `-m "not integration"` won't emit `PytestUnknownMarkWarning`. If a future test adds a new marker without registering it here, that warning becomes noise in CI logs that's easy to mistake for a real problem; keep marker registration and marker usage in sync.

- **`ci.yml` existing does not enforce anything by itself.** GitHub only blocks a merge on a failing/missing check if that check is explicitly added as a **required status check** under the repo's branch protection rules for `main` (Settings → Branches → Branch protection rule). Skipping this step means the green/red indicator is purely informational — a PR can still be merged while CI is red. This is the most common way a freshly-added CI workflow quietly does nothing.

- **`uv sync --frozen` vs plain `uv sync`.** `--frozen` fails the sync (and the whole job) if `uv.lock` is out of sync with `pyproject.toml`, instead of silently re-resolving and writing a new lock file inside the ephemeral runner. Without it, a stale committed lock file can pass CI while actually installing different versions than what's pinned — defeating the point of committing `uv.lock` at all. Always use `--frozen` in CI; never in local dev (there you *want* `uv sync` to update the lock).

- **Concurrency cancellation is a convenience, not a correctness requirement, for this workflow specifically** — since it does nothing but lint+test (no shared external state, no deploy), a canceled stale run can't leave anything partially applied. This is *not* true for Phases 18/19's CD workflows, where cancel-in-progress needs much more care (see those docs' Gotchas) — don't copy this workflow's `concurrency` block there unmodified.
