import os

import pytest

pytestmark = pytest.mark.integration


def test_openai_key_present():
    assert os.environ.get("OPENAI_API_KEY"), "OPENAI_API_KEY not set in .env"


def test_openai_chat_completion_reachable():
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(temperature=0)
    response = llm.invoke("Reply with exactly one word: pong")
    assert response.content.strip()


def test_tavily_key_present():
    assert os.environ.get("TAVILY_API_KEY"), "TAVILY_API_KEY not set in .env"


def test_tavily_search_reachable():
    from langchain_community.tools.tavily_search import TavilySearchResults

    tool = TavilySearchResults(k=1)
    results = tool.invoke({"query": "current weather in Paris"})
    assert results
