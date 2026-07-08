import os
import shutil
from pathlib import Path

from dotenv import load_dotenv
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_community.document_loaders import WebBaseLoader
from langchain_openai import OpenAIEmbeddings

load_dotenv()

# File-relative, not cwd-relative — this module is always imported as multi_agent.ingestion
# regardless of where a command is invoked from (backend/, multi_agent/, or elsewhere), so a
# "./.chroma" path resolved against the process cwd would silently point at the wrong
# directory (or a fresh empty one) whenever that cwd isn't exactly multi_agent/.
_CHROMA_SEED_DIR = Path(__file__).resolve().parent / ".chroma"

# Lambda's root filesystem is read-only outside /tmp (real AWS and LocalStack's emulation both
# enforce this) — Chroma's sqlite backend opens its file read-write even for pure reads, so the
# baked-in _CHROMA_SEED_DIR can't be opened in place there. CHROMA_PERSIST_DIR (set in
# infra/lambda.tf to /tmp/chroma) redirects to a writable copy instead; unset everywhere else
# (local dev, Docker Compose, tests), so this is a no-op there and _CHROMA_SEED_DIR is used
# directly, exactly as before.
_runtime_dir = os.environ.get("CHROMA_PERSIST_DIR")
if _runtime_dir:
    _CHROMA_DIR = Path(_runtime_dir)
    if not _CHROMA_DIR.exists():
        shutil.copytree(_CHROMA_SEED_DIR, _CHROMA_DIR)
else:
    _CHROMA_DIR = _CHROMA_SEED_DIR

urls = [
    "https://lilianweng.github.io/posts/2023-06-23-agent/",
    "https://lilianweng.github.io/posts/2023-03-15-prompt-engineering/",
    "https://lilianweng.github.io/posts/2023-10-25-adv-attack-llm/",
]

docs = [WebBaseLoader(url).load() for url in urls]
docs_list = [item for sublist in docs for item in sublist]

text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
    chunk_size=250, chunk_overlap=0
)
doc_splits = text_splitter.split_documents(docs_list)

# vectorstore = Chroma.from_documents(
#     documents=doc_splits,
#     collection_name="rag-chroma",
#     embedding=OpenAIEmbeddings(),
#     persist_directory=str(_CHROMA_DIR),
# )

retriever = Chroma(
    collection_name="rag-chroma",
    persist_directory=str(_CHROMA_DIR),
    embedding_function=OpenAIEmbeddings(),
).as_retriever()
