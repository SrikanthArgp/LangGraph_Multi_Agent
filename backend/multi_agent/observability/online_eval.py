"""Online evaluation: pushes the graph's own self-correction grades to Langfuse as scores
on the live production trace.

Reuses grade_generation()'s hallucination_grade/answer_grade (multi_agent/graph.py) instead
of running a separate RAGAS pass on live traffic — those grades are already computed on every
real chat turn to drive the generate/websearch retry loop, so this costs zero extra LLM calls.
Called from api/routers/chat.py as a FastAPI background task, after the chat response has
already been sent, so scoring latency never affects the user-facing request.
"""

import logging

from multi_agent.observability.langfuse_client import get_langfuse_client

logger = logging.getLogger(__name__)

GROUNDEDNESS_SCORE_NAME = "online_groundedness"
ANSWER_RELEVANCE_SCORE_NAME = "online_answer_relevance"


def score_generation_quality(
    trace_id: str | None,
    *,
    hallucination_grade: bool | None,
    answer_grade: bool | None,
) -> None:
    """Best-effort: must never raise, since it runs after the response is already returned."""
    if trace_id is None:
        return

    client = get_langfuse_client()
    if client is None:
        return

    try:
        if hallucination_grade is not None:
            client.create_score(
                trace_id=trace_id,
                name=GROUNDEDNESS_SCORE_NAME,
                value=1.0 if hallucination_grade else 0.0,
                data_type="BOOLEAN",
            )
        if answer_grade is not None:
            client.create_score(
                trace_id=trace_id,
                name=ANSWER_RELEVANCE_SCORE_NAME,
                value=1.0 if answer_grade else 0.0,
                data_type="BOOLEAN",
            )
    except Exception:
        logger.warning("online_eval_score_push_failed", exc_info=True)
