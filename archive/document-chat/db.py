import os  # Standard library module for reading environment variables
import re  # Standard library module for finding patterns in text

from dotenv import load_dotenv  # Loads settings from the .env file into environment variables
from langchain_core.documents import Document  # LangChain's container for a piece of text plus its metadata
from langchain_ollama import OllamaEmbeddings  # Turns text into vectors (numbers) using an Ollama model
from langchain_qdrant import QdrantVectorStore  # LangChain wrapper around a Qdrant collection
from qdrant_client import QdrantClient  # Low-level client that talks to Qdrant
from qdrant_client.models import (  # Settings and filters used with Qdrant
    Distance,  # How similarity between vectors is measured
    FieldCondition,  # One condition in a filter, e.g. "source equals X"
    Filter,  # A set of conditions for picking stored chunks
    FilterSelector,  # Tells delete() to remove whatever matches a filter
    MatchText,  # "Contains this word" (used to find exact codes like NAN0105)
    MatchValue,  # "Equals this exact value"
    VectorParams,  # Settings used when creating a collection
)  # End of imports

load_dotenv()  # Read .env (if it exists) so os.getenv can see our settings

COLLECTION = os.getenv("QDRANT_COLLECTION", "documents")  # Name of the Qdrant collection (like a table)
QDRANT_PATH = os.getenv("QDRANT_PATH", "qdrant_data")  # Folder where the local database is saved
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")  # Which Ollama model makes the vectors
TOP_K = int(os.getenv("TOP_K", "8"))  # How many chunks to pull from Qdrant for each question
CODE_PATTERN = re.compile(r"\b(?=[\w-]*\d)(?=[\w-]*[A-Za-z])[\w-]{4,}\b")  # Words mixing letters and digits, e.g. NAN0105


class PrefixedEmbeddings(OllamaEmbeddings):  # nomic-embed-text gives better results when told what each text is for
    def embed_documents(self, texts):  # Called when saving chunks
        return super().embed_documents(["search_document: " + t for t in texts])  # Mark them as documents

    def embed_query(self, text):  # Called when searching
        return super().embed_query("search_query: " + text)  # Mark it as a question


def source_filter(source, file_hash=None):  # Filter that picks the chunks of one file (optionally one version of it)
    conditions = [FieldCondition(key="metadata.source", match=MatchValue(value=source))]  # Same file
    if file_hash:  # A specific version was asked for
        conditions.append(FieldCondition(key="metadata.file_hash", match=MatchValue(value=file_hash)))  # Same content
    return Filter(must=conditions)  # All conditions must match


def delete_source(store, source):  # Removes every chunk that came from one file
    store.client.delete(  # Ask Qdrant to delete points
        collection_name=COLLECTION,  # From our collection
        points_selector=FilterSelector(filter=source_filter(source)),  # Whose source is this file
    )  # End of delete


def count_source(store, source, file_hash):  # How many chunks of this exact file version are stored
    return store.client.count(COLLECTION, count_filter=source_filter(source, file_hash), exact=True).count  # Exact count


def stored_sources(store):  # Names of every file that has chunks in the database
    sources, offset = set(), None  # Results so far, and where the next page starts
    while True:  # Read the database page by page
        points, offset = store.client.scroll(  # Get one page of stored chunks
            COLLECTION, limit=1000, offset=offset, with_payload=["metadata.source"], with_vectors=False  # Only the file name
        )  # End of scroll
        sources.update(p.payload["metadata"]["source"] for p in points)  # Remember each file name
        if offset is None:  # No more pages
            return sources  # Done


def unique_docs(docs):  # Removes repeated chunks, keeping the first one seen
    seen = {}  # Text -> chunk
    for d in docs:  # Go through in order
        seen.setdefault(d.page_content, d)  # Only keep the first copy
    return list(seen.values())  # In the original order


def search(store, question, k=TOP_K):  # Finds the chunks most useful for a question
    exact = []  # Chunks that contain a code from the question, word for word
    for code in dict.fromkeys(CODE_PATTERN.findall(question)):  # Every code-like word in the question (no repeats)
        points, _ = store.client.scroll(  # Look for chunks that contain that exact word (upper/lower case ignored)
            COLLECTION,  # In our collection
            scroll_filter=Filter(must=[FieldCondition(key="page_content", match=MatchText(text=code))]),  # Containing the code
            limit=k,  # At most k per code
        )  # End of scroll
        exact += [Document(page_content=p.payload["page_content"], metadata=p.payload["metadata"]) for p in points]  # Keep them
    exact = unique_docs(exact)  # A chunk may contain several codes
    similar = store.similarity_search(question, k=k)  # Chunks closest in meaning
    return unique_docs(exact + similar)[: max(k, len(exact))]  # Exact matches first (all of them), then fill up to k


def get_vector_store():  # Opens (and creates if needed) the Qdrant vector database
    embedding_class = PrefixedEmbeddings if "nomic" in EMBEDDING_MODEL else OllamaEmbeddings  # Prefixes only help nomic models
    embeddings = embedding_class(  # Create the embedding model client
        model=EMBEDDING_MODEL,  # Which Ollama model makes the vectors
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),  # Where Ollama runs
    )  # End of embeddings setup

    url = os.getenv("QDRANT_URL")  # Address of a Qdrant server, if you run one (e.g. in Docker)
    if url:  # A server address was given
        client = QdrantClient(url=url, api_key=os.getenv("QDRANT_API_KEY"))  # Connect to that server
    else:  # No server given
        try:  # The local database can only be opened by one program at a time
            client = QdrantClient(path=QDRANT_PATH)  # Use a local database stored in a folder (no server needed)
        except RuntimeError as e:  # Another program already has it open
            if "already accessed" not in str(e):  # Some other problem
                raise  # Show the original error
            raise SystemExit(  # Stop with a clear message instead of a long error
                f"\nThe database folder '{QDRANT_PATH}' is already in use by another program.\n"  # What happened
                "Close the other one first (main.py, ingest.py or server.py), then try again.\n"  # What to do
                "Tip: type 'exit' in the terminal chat, or press Ctrl+C in a running server."  # How to close them
            ) from None  # Hide the long technical error

    if not client.collection_exists(COLLECTION):  # First run: the collection doesn't exist yet
        size = len(embeddings.embed_query("test"))  # Ask the model how many numbers each vector has
        client.create_collection(  # Create the collection
            collection_name=COLLECTION,  # Its name
            vectors_config=VectorParams(size=size, distance=Distance.COSINE),  # Vector size and how similarity is measured
        )  # End of collection creation

    return QdrantVectorStore(  # Hand back a LangChain vector store ready for adding and searching
        client=client,  # The Qdrant connection
        collection_name=COLLECTION,  # Which collection to use
        embedding=embeddings,  # How to turn text into vectors
    )  # End of vector store setup
