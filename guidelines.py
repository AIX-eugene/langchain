from langchain_core.tools import tool  # Turns a Python function into a tool the AI can call
from langchain_ollama import OllamaEmbeddings  # Turns text into vectors using an Ollama model
from langchain_qdrant import QdrantVectorStore  # LangChain wrapper around a Qdrant collection
from qdrant_client import QdrantClient  # Low-level client that talks to the Qdrant server

from config import COLLECTION, EMBEDDING_MODEL, QDRANT_API_KEY, QDRANT_URL, TOP_K  # Settings
from embed_server import embedding_url  # Where search embeddings run

MACEA_COLLECTION = 'macea_guidelines'
_stores = {}  # Collection -> vector store, opened on first use


def make_client():  # Connection to the Qdrant server (the same one n8n uses)
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)  # e.g. http://localhost:6333


def make_embeddings():  # The model that turns text into vectors
    return OllamaEmbeddings(model=EMBEDDING_MODEL, base_url=embedding_url(), keep_alive=-1)  # Plain nomic-embed-text, exactly as n8n stored the passages; on the processor-only Ollama copy so it never unloads the judge


def get_store(collection=COLLECTION):
    if collection not in _stores:
        _stores[collection] = QdrantVectorStore(  # Connect to the collection
            client=make_client(),  # The Qdrant server
            collection_name=collection,
            embedding=make_embeddings(),  # How search text becomes vectors
            content_payload_key="content",  # n8n saves each passage's text under "content"
            metadata_payload_key="metadata",  # ...and its details under "metadata"
        )  # End of connection
    return _stores[collection]


def search(query, k=TOP_K, collection=COLLECTION):
    return get_store(collection).similarity_search(query, k=k)


def passage_count():  # How many passages the collection holds (shown in the status panel)
    store = get_store()  # The collection
    return store.client.count(COLLECTION).count  # Number of stored passages


@tool
def asc_guidelines(query: str) -> str:
    """Search the ASC Philippines advertising guidelines (Code of Ethics and Manual of Procedures). Input: a short search query. Returns the most relevant rule passages."""
    return retrieve_guidelines('asc_guidelines', query)


@tool
def macea_guidelines(query: str) -> str:
    """Search uploaded MACEA guidelines for MACEA-specific design, site, and installation requirements. Use for questions explicitly about MACEA, including follow-up questions. Not the ASC advertising content rules."""
    return retrieve_guidelines('macea_guidelines', query)


SEARCH_COLLECTIONS = {'asc_guidelines': COLLECTION, 'macea_guidelines': MACEA_COLLECTION}


class GuidelineSourceUnavailable(RuntimeError):
    """Required grounding could not be retrieved."""


def retrieve_guidelines(tool_name, query, seen=None, require_sources=False):
    """Dispatch only to an allowed collection and preserve its provenance."""
    collection = SEARCH_COLLECTIONS[tool_name]
    authority = 'MACEA' if tool_name == 'macea_guidelines' else 'ASC'
    try:
        docs = search(query, collection=collection)
    except Exception as exc:
        message = f'{authority} search unavailable ({collection}). Do not infer that there are no requirements or substitute another authority. Tell the user this source could not be checked.'
        if require_sources:
            raise GuidelineSourceUnavailable(message) from exc
        return message
    if not docs:
        if require_sources:
            raise GuidelineSourceUnavailable(f'No passages found in {authority} ({collection}).')
        return f'No passages found in {authority} ({collection}). Try a different query; do not invent requirements.'
    return f'Source authority: {authority}; collection: {collection}\n' + format_passages(docs, seen, authority)


def format_passages(docs, seen=None, authority='ASC'):
    seen = set() if seen is None else seen  # Passages already sent in this check
    parts = []  # Text for each passage
    for i, d in enumerate(docs, start=1):  # Each passage
        text = d.page_content.strip()  # Its text
        key = (authority, text)
        location = '; '.join(f'{field}: {d.metadata[field]}' for field in ('source', 'page', 'sheet', 'row') if field in d.metadata)
        label = f'[{authority} Passage {i}]' + (f' ({location})' if location else '')
        parts.append(f'{label} (already shown above)' if key in seen else f'{label}\n{text}')
        seen.add(key)
    return "\n\n---\n\n".join(parts)  # All passages, separated
