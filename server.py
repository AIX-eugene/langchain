import json  # Standard library module for turning data into JSON text
import os  # Standard library module for reading environment variables
import threading  # Standard library module; we use a lock so only one task touches the database at a time
from pathlib import Path  # Standard library module for working with files and folders

import ollama  # Ollama's own client, used to check if Ollama is running and whether it uses the GPU
import uvicorn  # The web server that runs the app
from fastapi import FastAPI, File, HTTPException, UploadFile  # Web framework pieces
from fastapi.responses import FileResponse, StreamingResponse  # Ways to send a file or a live stream back to the browser
from langchain_core.messages import AIMessage, HumanMessage  # Message types used to rebuild the conversation
from pydantic import BaseModel  # Describes the shape of data the browser sends

import ingest  # Our file reading / adding code
from db import COLLECTION, EMBEDDING_MODEL, delete_source, get_vector_store, search  # Our Qdrant helpers
from rag import CHAT_MODEL, OLLAMA_URL, answer_stream, get_llm, model_capabilities, source_label  # Shared AI logic

app = FastAPI(title="Local Assistant")  # Create the web app
store = get_vector_store()  # Open the Qdrant database once, for the whole time the server runs
llm = get_llm()  # Create the chat model client once
db_lock = threading.Lock()  # Only one request may use the database at a time
STATIC_DIR = Path(__file__).parent / "static"  # Folder that holds the web page


class Message(BaseModel):  # One earlier message in the conversation
    role: str  # "user" or "assistant"
    content: str  # The message text


class ChatRequest(BaseModel):  # What the browser sends when you ask something
    message: str  # The new question
    history: list[Message] = []  # Earlier messages, so follow-ups make sense


def event(kind, **data):  # Builds one line of the live answer stream
    return json.dumps({"type": kind, **data}) + "\n"  # One JSON object per line


@app.get("/")  # The home page
def index():  # Sends the web page to the browser
    return FileResponse(STATIC_DIR / "index.html")  # The whole UI is in this one file


@app.get("/api/status")  # Health check shown in the sidebar
def status():  # Reports models, database size and whether Ollama uses the GPU
    with db_lock:  # Wait for our turn with the database
        chunks = store.client.count(COLLECTION).count  # How many chunks are stored
    info = {"chat_model": CHAT_MODEL, "embedding_model": EMBEDDING_MODEL, "chunks": chunks, "ollama": False, "device": None}  # Defaults
    info["tools"] = "tools" in model_capabilities()  # Can the model use the spreadsheet tool?
    try:  # Ollama might not be running
        loaded = ollama.Client(host=OLLAMA_URL).ps().models  # Models currently loaded in Ollama
        info["ollama"] = True  # Ollama answered
        chat = next((m for m in loaded if m.model == CHAT_MODEL), None)  # Is the chat model loaded right now?
        if chat:  # It is
            info["device"] = "GPU" if (chat.size_vram or 0) > 0 else "CPU"  # Memory on the graphics card means GPU
    except Exception:  # Could not reach Ollama
        pass  # Keep ollama=False
    return info  # Send it to the browser


@app.get("/api/documents")  # List of files in the knowledge base
def documents():  # Reads the documents folder
    return [  # One entry per file
        {"name": str(p.relative_to(ingest.DOCS_DIR)), "size": p.stat().st_size}  # File name (with subfolder) and size in bytes
        for p in ingest.find_files()  # Every supported file
    ]  # End of list


@app.post("/api/upload")  # Add new files from the browser
def upload(files: list[UploadFile] = File(...)):  # Receives one or more files
    names = [Path(f.filename or "").name for f in files]  # Keep only the file name, never a folder path from the browser
    for name in names:  # Check every file before saving any
        if Path(name).suffix.lower() not in ingest.EXTENSIONS or name.startswith("~$"):  # Unsupported type
            raise HTTPException(400, f"Unsupported file: {name}")  # Refuse the upload
    ingest.DOCS_DIR.mkdir(exist_ok=True)  # Make sure the documents folder exists
    saved = []  # Paths of saved files
    for f, name in zip(files, names):  # Save each file
        dest = ingest.DOCS_DIR / name  # Where it goes
        dest.write_bytes(f.file.read())  # Write it to disk (replaces a file with the same name)
        saved.append(dest)  # Remember it
    with db_lock:  # Wait for our turn with the database
        count = ingest.ingest_files(store, saved)  # Read, split and embed the new files
    return {"files": len(saved), "chunks": count}  # Report what was added


@app.delete("/api/documents/{name:path}")  # Remove a file from the knowledge base
def delete_document(name: str):  # name is the file name shown in the list
    docs_dir = ingest.DOCS_DIR.resolve()  # Full path of the documents folder
    target = (docs_dir / name).resolve()  # Full path of the file to delete
    if docs_dir not in target.parents or not target.is_file():  # Refuse anything outside the documents folder
        raise HTTPException(404, "File not found")  # Tell the browser
    with db_lock:  # Wait for our turn with the database
        delete_source(store, str(ingest.DOCS_DIR / target.relative_to(docs_dir)))  # Remove its chunks from Qdrant
    target.unlink()  # Delete the file itself
    return {"deleted": name}  # Confirm


@app.post("/api/chat")  # Ask a question
def chat(req: ChatRequest):  # Streams the answer back piece by piece
    def stream():  # Produces the live answer
        try:  # Report errors to the browser instead of crashing
            with db_lock:  # Wait for our turn with the database
                docs = search(store, req.message)  # Find the most relevant chunks (exact codes + closest meaning)
            yield event("sources", sources=list(dict.fromkeys(source_label(d, with_row=False) for d in docs)))  # Which files were used
            history = [  # Rebuild earlier messages for the model
                HumanMessage(m.content) if m.role == "user" else AIMessage(m.content)  # Right type for each message
                for m in req.history[-10:]  # Only the last 10, so the prompt stays small
            ]  # End of history
            for kind, data in answer_stream(llm, req.message, history, docs):  # Answer, querying spreadsheets if needed
                if kind == "tool":  # A spreadsheet query was run
                    yield event("tool", **data)  # Show it in the chat
                else:  # Thinking or answer text
                    yield event(kind, text=data)  # Send it
            yield event("done")  # Tell the browser the answer is complete
        except Exception as e:  # Something went wrong (e.g. Ollama not running)
            yield event("error", message=str(e))  # Show the error in the chat

    return StreamingResponse(stream(), media_type="application/x-ndjson")  # Send lines as they are produced


if __name__ == "__main__":  # Only run when this file is executed directly
    port = int(os.getenv("PORT", "8000"))  # Which port to use (8000 unless set in .env)
    print(f"Open http://127.0.0.1:{port} in your browser")  # Tell the user where to go
    uvicorn.run(app, host="127.0.0.1", port=port)  # Only this computer can reach it (127.0.0.1)
