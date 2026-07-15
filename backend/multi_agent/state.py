from typing import List, TypedDict


class GraphState(TypedDict):
    """
    Represents the state of our graph.

    Attributes:
        question: question
        generation: LLM generation
        web_search: whether to add search
        documents: list of documents
        hallucination_grade: whether the last generation was grounded in documents
            (None if the grader was unavailable and the generation was accepted regardless)
        answer_grade: whether the last generation addressed the question
            (None if the grader was unavailable, or hallucination_grade was False so
            answer grading was skipped)
    """

    question: str
    generation: str
    web_search: bool
    documents: List[str]
    hallucination_grade: bool | None
    answer_grade: bool | None
