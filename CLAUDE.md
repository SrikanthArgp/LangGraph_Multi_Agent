# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

Copy `.env.example` to `.env` and fill in your API keys:
- `OPENAI_API_KEY` — used by all chains and embeddings
- `TAVILY_API_KEY` — used by the web search node
- `LANGCHAIN_API_KEY` / `LANGCHAIN_TRACING_V2` / `LANGCHAIN_PROJECT` — optional LangSmith tracing

Before running the graph for the first time, populate the Chroma vector store by uncommenting the `Chroma.from_documents(...)` block in `ingestion.py` and running it once. After the store is built, re-comment that block so subsequent runs use the persisted `.chroma/` directory.

## Commands

```bash
# Run the agent end-to-end
python main.py

# Run all tests (integration tests hit real LLMs — require valid API keys)
pytest chains/tests/

# Run a single test
pytest chains/tests/test_chains.py::test_router_to_vectorstore
```

## Architecture

This is a **Corrective RAG (CRAG)** multi-agent pipeline built with LangGraph. The graph routes questions either to a local vector store or to web search, grades retrieved documents for relevance, generates an answer, then grades the answer for hallucinations and usefulness before returning.

### Graph flow (`graph.py`)

```
question → route_question
              ├─► websearch → generate
              └─► retrieve → grade_documents
                                ├─► generate (all docs relevant)
                                └─► websearch → generate (some docs irrelevant)

generate → grade_generation_grounded_in_documents_and_question
              ├─► END          (useful)
              ├─► websearch    (not useful — retry with web results)
              └─► generate     (not supported — hallucination detected, retry)
```

Node constants (`RETRIEVE`, `GRADE_DOCUMENTS`, `GENERATE`, `WEBSEARCH`) are defined in `consts.py`.

### State (`state.py`)

`GraphState` is a `TypedDict` with four fields passed between every node:
- `question` — the original user question
- `documents` — list of retrieved/filtered `Document` objects
- `generation` — the LLM's answer string
- `web_search` — flag set by `grade_documents` to trigger a web search fallback

### Chains (`chains/`)

Each file builds a standalone LangChain runnable (prompt | LLM | parser):

| File | Purpose | Output type |
|---|---|---|
| `router.py` | Routes question to `vectorstore` or `websearch` | `RouteQuery` (structured) |
| `retrieval_grader.py` | Scores a single document for relevance | `GradeDocuments` (binary `"yes"/"no"`) |
| `generation.py` | Generates an answer from context | `str` (via `rlm/rag-prompt` from LangChain Hub) |
| `hallucination_grader.py` | Checks if generation is grounded in documents | `GradeHallucinations` (binary `bool`) |
| `answer_grader.py` | Checks if generation addresses the question | `GradeAnswer` (binary `bool`) |

All chains use `ChatOpenAI(temperature=0)` with structured output via Pydantic models where grading is required.

### Nodes (`nodes/`)

Thin wrappers that call the chains and return updated state slices:
- `retrieve` — queries the Chroma retriever from `ingestion.py`
- `grade_documents` — iterates documents through `retrieval_grader`; sets `web_search=True` if any doc is irrelevant
- `generate` — calls `generation_chain`
- `web_search` — calls `TavilySearchResults(k=3)` and appends results as a `Document`

### Vector store (`ingestion.py` + `.chroma/`)

Documents are loaded from three Lilian Weng blog posts (agents, prompt engineering, adversarial attacks), split with `RecursiveCharacterTextSplitter` (chunk size 250, no overlap), embedded with `OpenAIEmbeddings`, and stored in a local Chroma collection named `rag-chroma`.

### Memory / checkpointing (`graph.py`)

The compiled graph uses `MemorySaver` (in-memory). Queries in `main.py` pass `thread_id` via `config={"configurable": {"thread_id": "..."}}` for conversation-level state isolation.
