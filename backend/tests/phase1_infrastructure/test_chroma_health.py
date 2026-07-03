import pytest

pytestmark = pytest.mark.integration


def test_collection_returns_documents(chroma_retriever):
    docs = chroma_retriever.invoke("agent memory")
    assert len(docs) > 0
    assert all(doc.page_content for doc in docs)


def test_collection_covers_multiple_source_topics(chroma_retriever):
    agent_docs = chroma_retriever.invoke("what are the types of agent memory")
    prompt_docs = chroma_retriever.invoke("chain of thought prompting")
    assert len(agent_docs) > 0
    assert len(prompt_docs) > 0
