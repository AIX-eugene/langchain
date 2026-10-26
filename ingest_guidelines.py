"""Adds a guideline PDF (e.g. the ASC Guidebook) to the asc_guidelines collection.

Usage:
    uv run ingest_guidelines.py "path\\to\\ASC Guidebook.pdf"            add a PDF
    uv run ingest_guidelines.py "path\\to\\ASC Guidebook.pdf" --replace  replace an earlier copy of the same file

This does the same as the "PDF form -> Qdrant Vector Store" branch of the n8n workflow, and stores
passages in the same format, so passages added here and by n8n can be searched together.
"""

import sys  # Standard library module for command-line arguments
import uuid  # Standard library module for making unique IDs
from pathlib import Path  # Standard library module for working with file paths

from langchain_core.documents import Document  # LangChain's container for a piece of text plus its metadata
from langchain_text_splitters import RecursiveCharacterTextSplitter  # Cuts long text into smaller passages
from pypdf import PdfReader  # Reads text out of PDF files
from qdrant_client.models import Distance, FieldCondition, Filter, FilterSelector, MatchValue, VectorParams  # Qdrant settings and filters

from config import COLLECTION  # Collection name
from guidelines import get_store, make_client, make_embeddings  # The asc_guidelines collection and its helpers

BATCH_SIZE = 32  # Passages embedded at a time (progress is shown after each batch)


def main():  # Entry point of the program
    args = [a for a in sys.argv[1:] if not a.startswith("--")]  # File paths given
    replace = "--replace" in sys.argv  # Replace an earlier copy?
    if len(args) != 1 or not args[0].lower().endswith(".pdf"):  # Wrong usage
        sys.exit(__doc__)  # Show how to use it
    path = Path(args[0])  # The PDF
    if not path.is_file():  # Doesn't exist
        sys.exit(f"File not found: {path}")  # Explain

    client = make_client()  # Connection to the Qdrant server
    if not client.collection_exists(COLLECTION):  # First time: create the collection
        size = len(make_embeddings().embed_query("test"))  # How many numbers each vector has (768 for nomic-embed-text)
        client.create_collection(COLLECTION, vectors_config=VectorParams(size=size, distance=Distance.COSINE))  # Same settings as n8n
        print(f"Created collection '{COLLECTION}'.")  # Report
    store = get_store()  # Open the collection for adding passages

    same_file = Filter(must=[FieldCondition(key="metadata.source", match=MatchValue(value=path.name))])  # Passages from this file name
    existing = client.count(COLLECTION, count_filter=same_file, exact=True).count  # How many there are
    if existing and not replace:  # Already added
        sys.exit(f"'{path.name}' is already in the collection ({existing} passages). Add --replace to replace it.")  # Don't duplicate
    if existing:  # Replacing
        client.delete(COLLECTION, points_selector=FilterSelector(filter=same_file))  # Remove the old copy
        print(f"Removed {existing} old passages of '{path.name}'.")  # Report
    total = client.count(COLLECTION).count  # Passages already in the collection (e.g. added by n8n)
    if total and not existing:  # Something else is there already
        answer = input(f"The collection already has {total} passages (for example, added by n8n). If this is the same "  # Warn about duplicates
                       f"guidebook, adding it again creates duplicates. Continue? [y/N] ")  # Ask
        if answer.strip().lower() != "y":  # Not confirmed
            sys.exit("Cancelled.")  # Stop

    pages = [  # One Document per PDF page
        Document(page_content=page.extract_text() or "", metadata={"source": path.name, "page": n})  # Page text, file name and page number
        for n, page in enumerate(PdfReader(path).pages, start=1)  # Every page, numbered from 1
    ]  # End of pages
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)  # Same sizes as the n8n text splitter
    chunks = [c for c in splitter.split_documents(pages) if c.page_content.strip()]  # Passages with text
    if not chunks:  # Nothing readable (a scanned PDF)
        sys.exit("No text found in this PDF. It may be a scanned document; run it through OCR first.")  # Explain

    print(f"Adding {len(chunks)} passages from {len(pages)} pages of '{path.name}'...")  # Start
    ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, f"{path.name}:{i}")) for i in range(len(chunks))]  # Stable ID per passage
    for start in range(0, len(chunks), BATCH_SIZE):  # One batch at a time
        end = min(start + BATCH_SIZE, len(chunks))  # Last passage of this batch
        store.add_documents(chunks[start:end], ids=ids[start:end])  # Embed and save them
        print(f"  {end}/{len(chunks)} ({end * 100 // len(chunks)}%)")  # Progress
    print(f"Done. The collection now holds {client.count(COLLECTION).count} passages.")  # Report


if __name__ == "__main__":  # Only run when this file is executed directly
    main()  # Start
