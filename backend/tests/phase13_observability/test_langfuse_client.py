from langfuse.langchain import CallbackHandler

from multi_agent.observability import langfuse_client


def test_get_langfuse_handler_returns_handler_without_raising():
    """Per plan.md Phase 13 step 4: a missing/misconfigured Langfuse key should fail fast
    here in CI rather than silently disabling tracing in production. The installed SDK
    (langfuse==4.13.0) never actually raises from CallbackHandler() - even with keys unset,
    it logs an auth warning and returns a disabled-but-usable handler - so the meaningful
    assertion is that construction succeeds and yields a real handler, not None.
    """
    handler = langfuse_client.get_langfuse_handler()
    assert isinstance(handler, CallbackHandler)


def test_get_langfuse_handler_returns_none_on_unexpected_construction_error(monkeypatch):
    """Exercises the except branch directly, since the real SDK doesn't raise on its own -
    confirms get_langfuse_handler() degrades to None instead of propagating, so a
    Langfuse-side outage/incompatibility can never take down a graph run.
    """

    def _raise() -> CallbackHandler:
        raise RuntimeError("simulated construction failure")

    monkeypatch.setattr(langfuse_client, "CallbackHandler", _raise)

    assert langfuse_client.get_langfuse_handler() is None
