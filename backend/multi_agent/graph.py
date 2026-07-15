import logging

from dotenv import load_dotenv

load_dotenv()

from langgraph.graph import END, START, StateGraph
from tenacity import retry, stop_after_attempt, wait_exponential

from multi_agent.chains.answer_grader import answer_grader
from multi_agent.chains.hallucination_grader import hallucination_grader
from multi_agent.chains.router import question_router, RouteQuery
from multi_agent.consts import GENERATE, GRADE_DOCUMENTS, GRADE_GENERATION, RETRIEVE, WEBSEARCH
from multi_agent.nodes import generate, grade_documents, retrieve, web_search
from multi_agent.state import GraphState

logger = logging.getLogger(__name__)

_RETRY = dict(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=4), reraise=False)


@retry(**_RETRY)
def _route_question(question: str) -> RouteQuery:
    return question_router.invoke({"question": question})  # type: ignore


@retry(**_RETRY)
def _grade_hallucination(documents, generation):
    return hallucination_grader.invoke(
        {"documents": documents, "generation": generation}
    )


@retry(**_RETRY)
def _grade_answer(question, generation):
    return answer_grader.invoke({"question": question, "generation": generation})


def decide_to_generate(state):
    print("---ASSESS GRADED DOCUMENTS---")

    if state["web_search"]:
        print(
            "---DECISION: NOT ALL DOCUMENTS ARE NOT RELEVANT TO QUESTION, INCLUDE WEB SEARCH---"
        )
        return WEBSEARCH
    else:
        print("---DECISION: GENERATE---")
        return GENERATE


def grade_generation(state: GraphState) -> dict:
    """Grades the latest generation and writes the results to state.

    Split out from the routing decision (decide_generation_quality) so the grades survive
    past this single conditional-edge evaluation: LangGraph conditional-edge functions can't
    mutate state, only nodes can, and these grades are also pushed to Langfuse as online eval
    scores once the graph run completes (api/routers/chat.py) — reusing this self-correction
    grading instead of a separate scoring pass costs zero extra LLM calls.
    """
    print("---CHECK HALLUCINATIONS---")
    question = state["question"]
    documents = state["documents"]
    generation = state["generation"]

    try:
        hallucination_grade = _grade_hallucination(documents, generation).binary_score
    except Exception:
        logger.warning("hallucination_grading_failed", exc_info=True)
        print("---HALLUCINATION CHECK UNAVAILABLE, ACCEPTING GENERATION---")
        return {"hallucination_grade": None, "answer_grade": None}

    if not hallucination_grade:
        print("---DECISION: GENERATION IS NOT GROUNDED IN DOCUMENTS, RE-TRY---")
        return {"hallucination_grade": False, "answer_grade": None}

    print("---DECISION: GENERATION IS GROUNDED IN DOCUMENTS---")
    print("---GRADE GENERATION vs QUESTION---")
    try:
        answer_grade = _grade_answer(question, generation).binary_score
    except Exception:
        logger.warning("answer_grading_failed", exc_info=True)
        print("---ANSWER CHECK UNAVAILABLE, ACCEPTING GENERATION---")
        return {"hallucination_grade": True, "answer_grade": None}

    return {"hallucination_grade": True, "answer_grade": answer_grade}


def decide_generation_quality(state: GraphState) -> str:
    hallucination_grade = state.get("hallucination_grade")
    answer_grade = state.get("answer_grade")

    if hallucination_grade is False:
        return "not supported"
    if hallucination_grade is None or answer_grade is None:
        # Grader unavailable at some point — accept rather than loop indefinitely
        # between generate/websearch on a degraded grader.
        return "useful"

    if answer_grade:
        print("---DECISION: GENERATION ADDRESSES QUESTION---")
        return "useful"
    else:
        print("---DECISION: GENERATION DOES NOT ADDRESS QUESTION---")
        return "not useful"


def route_question(state: GraphState) -> str:
    print("---ROUTE QUESTION---")
    question = state["question"]
    try:
        source = _route_question(question)
    except Exception:
        logger.warning("routing_failed", exc_info=True)
        print("---ROUTING UNAVAILABLE, DEFAULTING TO WEB SEARCH---")
        return WEBSEARCH

    if source.datasource == WEBSEARCH:
        print("---ROUTE QUESTION TO WEB SEARCH---")
        return WEBSEARCH
    elif source.datasource == "vectorstore":
        print("---ROUTE QUESTION TO RAG---")
        return RETRIEVE


workflow = StateGraph(GraphState)
workflow.add_node(RETRIEVE, retrieve)
workflow.add_node(GRADE_DOCUMENTS, grade_documents)
workflow.add_node(GENERATE, generate)
workflow.add_node(WEBSEARCH, web_search)
workflow.add_node(GRADE_GENERATION, grade_generation)


workflow.add_conditional_edges(
    START,
    route_question,
    {
        WEBSEARCH: WEBSEARCH,
        RETRIEVE: RETRIEVE,
    },
)
workflow.add_edge(RETRIEVE, GRADE_DOCUMENTS)
workflow.add_conditional_edges(
    GRADE_DOCUMENTS,
    decide_to_generate,
    {
        WEBSEARCH: WEBSEARCH,
        GENERATE: GENERATE,
    },
)
workflow.add_edge(WEBSEARCH, GENERATE)
workflow.add_edge(GENERATE, GRADE_GENERATION)
workflow.add_conditional_edges(
    GRADE_GENERATION,
    decide_generation_quality,
    {
        "not supported": GENERATE,
        "useful": END,
        "not useful": WEBSEARCH,
    },
)


def create_app(checkpointer):
    """Compile and return the CRAG graph with the given checkpointer."""
    return workflow.compile(checkpointer=checkpointer)
