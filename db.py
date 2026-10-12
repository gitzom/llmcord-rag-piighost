import asyncio
import lancedb
import re

import io
import os

# Load .env (if present) BEFORE the embedding model is created, so machine-specific
# flags like HF_HUB_OFFLINE=1 can live in .env instead of being hardcoded here.
from dotenv import load_dotenv

load_dotenv()

# Force UTF-8 stdio so non-ASCII text doesn't crash Windows consoles.
os.environ["PYTHONIOENCODING"] = "utf-8"


db = lancedb.connect("./lancedb")


from lancedb.embeddings import get_registry
from lancedb.pydantic import LanceModel, Vector

embeddings = (
    get_registry().get("sentence-transformers")
    .create(name="BAAI/bge-small-en-v1.5")
)


class Messages(LanceModel):
    vector: Vector(embeddings.ndims()) = embeddings.VectorField()
    text: str = embeddings.SourceField()

try:
    table = db.open_table("documents")
except Exception:
    table = db.create_table("documents", schema=Messages)

def chunk(text_data):
    separator = "==== CONVO ===|---"
    splits = re.split(separator, text_data)
    return [s.strip() for s in splits if s.strip()]

def vectorization(chunked_data, init = False):
    data = [{"text": c} for c in chunked_data]

    table.add(data)
    if init:
        table.create_fts_index("text", replace=True)
    return table   


def search_docs(query: str, top_k: int = 5):
    results = table.search(query).limit(top_k).to_list()
    return [{"text": r["text"], "score": 1 - r["_distance"]} for r in results]


# --- Async wrappers (for use inside the bot's event loop) ---
# Embedding (PyTorch) and LanceDB (Rust) both release the GIL, so running them
# on a worker thread via to_thread gives real parallelism with the event loop.

async def search_docs_async(query: str, top_k: int = 5) -> list[dict]:
    return await asyncio.to_thread(search_docs, query, top_k)


async def add_docs_async(texts: list[str], create_index: bool = False) -> None:
    await asyncio.to_thread(vectorization, texts, create_index)

if __name__ == "__main__":
    print(search_docs("two people being friends"))
    print(search_docs("two people being evil"))
    print(search_docs("soylent"))