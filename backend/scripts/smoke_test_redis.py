"""One-off Redis connectivity smoke test, isolated from the app's own config.

Loads REDIS_URL from a separate env file (default backend/.env.upstash), NOT
backend/.env — so verifying a managed Redis provider never risks touching the
REDIS_URL that local `python run_api.py` runs read. Docker Compose is unaffected
either way (it force-overrides REDIS_URL for the container regardless).

Usage:
    python scripts/smoke_test_redis.py [--env-file .env.upstash]
"""

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import dotenv_values


async def main(env_file: str) -> int:
    path = Path(__file__).resolve().parent.parent / env_file
    if not path.exists():
        print(f"FAIL: {path} not found")
        return 1

    values = dotenv_values(path)
    redis_url = values.get("REDIS_URL")
    if not redis_url:
        print(f"FAIL: REDIS_URL not set in {path}")
        return 1

    import redis.asyncio as aioredis

    client = aioredis.from_url(redis_url, decode_responses=True)
    try:
        pong = await client.ping()
        print(f"PING -> {pong}")

        await client.set("smoke_test", "ok", ex=10)
        val = await client.get("smoke_test")
        print(f"GET smoke_test -> {val}")
        await client.delete("smoke_test")

        policy = await client.config_get("maxmemory-policy")
        print(f"maxmemory-policy -> {policy.get('maxmemory-policy')}")
    finally:
        await client.aclose()

    print("PASS")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", default=".env.upstash")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.env_file)))
