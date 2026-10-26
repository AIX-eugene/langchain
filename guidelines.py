from langchain_core.tools import tool  # Turns a Python function into a tool the AI can call
from langchain_ollama import OllamaEmbeddings  # Turns text into vectors using an Ollama model
from langchain_qdrant import QdrantVectorStore  # LangChain wrapper around a Qdrant collection
from qdrant_client import QdrantClient  # Low-level client that talks to the Qdrant server

from config import COLLECTION, EMBEDDING_MODEL, QDRANT_API_KEY, QDRANT_URL, TOP_K  # Settings
from embed_server import embedding_url  # Where search embeddings run

_store = None  # The opened collection, created on first use


def make_client():  # Connection to the Qdrant server (the same one n8n uses)
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)  # e.g. http://localhost:6333


def make_embeddings():  # The model that turns text into vectors
    return OllamaEmbeddings(model=EMBEDDING_MODEL, base_url=embedding_url(), keep_alive=-1)  # Plain nomic-embed-text, exactly as n8n stored the passages; on the processor-only Ollama copy so it never unloads the judge


def get_store():  # Opens the asc_guidelines collection on the Qdrant server (once). The collection must already exist
    global _store  # Reuse the same connection every time
    if _store is None:  # Not opened yet
        _store = QdrantVectorStore(  # Connect to the collection
            client=make_client(),  # The Qdrant server
            collection_name=COLLECTION,  # asc_guidelines
            embedding=make_embeddings(),  # How search text becomes vectors
            content_payload_key="content",  # n8n saves each passage's text under "content"
            metadata_payload_key="metadata",  # ...and its details under "metadata"
        )  # End of connection
    return _store  # Hand it back


def search(query, k=TOP_K):  # Finds the guideline passages closest in meaning to a query
    return get_store().similarity_search(query, k=k)  # The k best passages


def passage_count():  # How many passages the collection holds (shown in the status panel)
    store = get_store()  # The collection
    return store.client.count(COLLECTION).count  # Number of stored passages


@tool
def asc_guidelines(query: str) -> str:
    """Search the ASC Philippines advertising guidelines (Code of Ethics and Manual of Procedures). Input: a short search query. Returns the most relevant rule passages."""
    docs = search(query)  # The best-matching passages
    if not docs:  # Nothing found
        return "No passages found. Try a different query."  # Tell the AI
    return format_passages(docs)  # Numbered passages


def format_passages(docs, seen=None):  # Numbers the passages; ones already shown earlier are not repeated (saves room in the judge's memory)
    seen = set() if seen is None else seen  # Passages already sent in this check
    parts = []  # Text for each passage
    for i, d in enumerate(docs, start=1):  # Each passage
        text = d.page_content.strip()  # Its text
        parts.append(f"[Passage {i}] (already shown above)" if text in seen else f"[Passage {i}]\n{text}")  # Full text only the first time
        seen.add(text)  # Remember it
    return "\n\n---\n\n".join(parts)  # All passages, separated
