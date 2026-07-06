# Build context is backend/ itself (see docker-compose.yml's `backend.build.context`) — this
# image never needs anything from outside backend/, so there's no reason to build from the repo
# root. frontend/Dockerfile follows the same pattern with its own context.
FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

# Dependency layer first, separate from source, so `docker build` skips `uv sync` on
# source-only changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --extra prod

COPY . ./

EXPOSE 8000

# Same entrypoint as local dev (`python run_api.py`, not `uvicorn api.main:app`) — see that
# file's docstring. The Windows event-loop issue it works around doesn't apply in this Linux
# container, but keeping one entrypoint avoids a second code path to maintain.
CMD ["uv", "run", "python", "run_api.py"]
