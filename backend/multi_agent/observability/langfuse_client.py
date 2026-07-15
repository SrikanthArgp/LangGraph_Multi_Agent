import logging

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

logger = logging.getLogger(__name__)


def get_langfuse_handler() -> CallbackHandler | None:
    """Build a Langfuse callback handler from LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY /
    LANGFUSE_HOST in the environment.

    Returns None instead of raising if Langfuse isn't configured or unreachable, so tracing
    being unavailable never blocks a graph run (see Resilience & Crash Prevention in plan.md).
    Callers should skip adding the handler to callbacks when this returns None.
    """
    try:
        return CallbackHandler()
    except Exception:
        logger.warning("langfuse_handler_unavailable", exc_info=True)
        return None


def get_langfuse_client() -> Langfuse | None:
    """Build a Langfuse client for direct API calls (e.g. create_score), same env vars and
    same never-block-the-caller contract as get_langfuse_handler above."""
    try:
        return Langfuse()
    except Exception:
        logger.warning("langfuse_client_unavailable", exc_info=True)
        return None
