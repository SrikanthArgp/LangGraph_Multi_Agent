# Build context is backend/ itself (see docker-compose.yml's `backend.build.context`) — this
# image never needs anything from outside backend/, so there's no reason to build from the repo
# root. frontend/Dockerfile follows the same pattern with its own context.
FROM python:3.12-slim

# Lambda Extension that runs the real uvicorn process and proxies Lambda invocations to it —
# not Mangum, which buffers the whole ASGI response and can't relay a StreamingResponse/SSE.
# A no-op outside Lambda: nothing invokes the Runtime Interface Client locally/in Compose, so
# `docker run`/`docker compose up` behavior is unchanged (verify before any Terraform exists).
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.8.4 /lambda-adapter /opt/extensions/lambda-adapter
ENV PORT=8000

# AWS_LWA_INVOKE_MODE deliberately NOT set here (defaults to the adapter's own "buffered" mode).
# One Lambda *function* can only speak one invoke mode to the adapter, but this same image is
# deployed as two separate functions in infra/lambda-gate/lambda.tf — a plain one behind API Gateway
# (buffered) and a second with AWS_LWA_INVOKE_MODE=RESPONSE_STREAM set only via that function's
# Terraform-level environment variables, behind the streaming Function URL. Baking RESPONSE_STREAM
# in here broke the API-Gateway-fronted function: API Gateway's HTTP API integration always uses
# a classic buffered Invoke (never InvokeWithResponseStream), so it can't parse the adapter's
# streaming-format output (a JSON prelude + 8 null bytes + body) — found by actually invoking it
# through LocalStack's API Gateway emulation, not assumed (Phase 15 Stage B).


RUN pip install --no-cache-dir uv

WORKDIR /app

# Dependency layer first, separate from source, so `docker build` skips `uv sync` on
# source-only changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --extra prod

COPY . ./

EXPOSE 8000

# Lambda (real and LocalStack-emulated) only guarantees /tmp as writable at runtime — the
# execution environment's own home directory isn't. `uv run` needs a cache dir, and defaults to
# $HOME/.cache/uv; without this override it 500s inside Lambda with a cache-dir permission error
# ("Permission denied: /home/sbx_user1051/.cache/uv" under LocalStack's sandboxed runtime user)
# even though the same image runs fine in plain `docker run`/Compose, where $HOME is writable.
ENV UV_CACHE_DIR=/tmp/uv-cache

# Same entrypoint as local dev (`python run_api.py`, not `uvicorn api.main:app`) — see that
# file's docstring. The Windows event-loop issue it works around doesn't apply in this Linux
# container, but keeping one entrypoint avoids a second code path to maintain.
# Split into ENTRYPOINT+CMD (equivalent to a single CMD when run with no override args) because
# LocalStack's container-image Lambda executor inspects the image's Config.Entrypoint and 500s
# with `KeyError: 'Entrypoint'` if it's unset — real AWS Lambda + the Web Adapter tolerates
# CMD-only, this split is purely for LocalStack compatibility (verified empirically, Phase 15
# Stage B).
ENTRYPOINT ["uv", "run", "python"]
CMD ["run_api.py"]
