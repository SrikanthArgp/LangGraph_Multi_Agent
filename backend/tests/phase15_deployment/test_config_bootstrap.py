import os

import pytest

from config import _SSM_SECRET_KEYS, _bootstrap_from_ssm, bootstrap_env


class _FakeSSMClient:
    """Stands in for boto3's real SSM client - no network/LocalStack call needed, matching
    Phase 14's InMemorySpanExporter precedent for testing a cold-start bootstrap path offline.
    """

    def __init__(self, values_by_name: dict[str, str]):
        self._values_by_name = values_by_name

    def get_parameter(self, Name: str, WithDecryption: bool):
        assert WithDecryption is True
        return {"Parameter": {"Value": self._values_by_name[Name]}}


def test_bootstrap_env_takes_the_dotenv_branch_when_not_production(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    calls = []
    monkeypatch.setattr("config.load_dotenv", lambda: calls.append("dotenv"))
    monkeypatch.setattr("config._bootstrap_from_ssm", lambda: calls.append("ssm"))

    bootstrap_env()

    assert calls == ["dotenv"]


def test_bootstrap_env_takes_the_ssm_branch_when_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    calls = []
    monkeypatch.setattr("config.load_dotenv", lambda: calls.append("dotenv"))
    monkeypatch.setattr("config._bootstrap_from_ssm", lambda: calls.append("ssm"))

    bootstrap_env()

    assert calls == ["ssm"]


def test_bootstrap_from_ssm_populates_os_environ_for_every_secret_key(monkeypatch):
    prefix = "/crag/prod"
    monkeypatch.setenv("SSM_PARAMETER_PREFIX", prefix)
    values_by_name = {f"{prefix}/{key}": f"value-for-{key}" for key in _SSM_SECRET_KEYS}
    monkeypatch.setattr("boto3.client", lambda service_name: _FakeSSMClient(values_by_name))

    # Snapshot real values (loaded from .env at session start by conftest.py) before
    # overwriting them - monkeypatch.delenv/setenv can't do this cleanup safely here, since
    # _bootstrap_from_ssm mutates os.environ directly (not through monkeypatch), so
    # monkeypatch has no record of what was there beforehand to restore. Getting this wrong
    # previously leaked fake "value-for-REDIS_URL" etc. into every other test in the same
    # pytest session that runs after this one and reads a real DATABASE_URL/REDIS_URL/etc.
    original_values = {key: os.environ.get(key) for key in _SSM_SECRET_KEYS}
    try:
        _bootstrap_from_ssm()
        for key in _SSM_SECRET_KEYS:
            assert os.environ[key] == f"value-for-{key}"
    finally:
        for key, value in original_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_bootstrap_from_ssm_raises_on_missing_parameter(monkeypatch):
    """A missing SSM parameter should fail cold start loudly, not start the app half-configured
    - same "fail-fast, not suppressed" precedent as api/main.py's lifespan DB/Redis checks.
    """
    monkeypatch.setenv("SSM_PARAMETER_PREFIX", "/crag/prod")
    monkeypatch.setattr("boto3.client", lambda service_name: _FakeSSMClient({}))

    with pytest.raises(KeyError):
        _bootstrap_from_ssm()
