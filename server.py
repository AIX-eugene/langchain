import json  # Standard library module for turning data into JSON text
import re  # Standard library module for cleaning up file names
import threading  # Standard library module; a lock makes checks run one at a time (they share the graphics card)
import queue
from datetime import datetime  # Standard library module for the date in the report's file name
from pathlib import Path  # Standard library module for working with files and folders

import ollama  # Ollama's own client, used to check that Ollama and the models are available
import uvicorn  # The web server that runs the app
from fastapi import FastAPI, File, Form, HTTPException, UploadFile  # Web framework pieces
from fastapi.responses import FileResponse, Response, StreamingResponse  # Ways to send a file, a PDF or a live stream back to the browser

import guidelines  # The asc_guidelines collection on the Qdrant server
from document_ingestion import UPLOAD_COLLECTION, ingest_document, read_upload, source_name
from config import (  # Settings
    CHAT_CONTEXT_CHARS,  # Memory limit per chat, in characters
    CHAT_CONTEXT_LIMIT,  # The same limit in tokens
    COLLECTION,  # Guidelines collection name
    EMBEDDING_MODEL,  # Search model
    IMAGE_TYPES,  # Accepted image files
    JUDGE_MODEL,  # Step 2 model
    MAX_IMAGE_MB,  # Largest image accepted
    OLLAMA_URL,  # Where Ollama runs
    PORT,  # Web page port
    QDRANT_URL,  # Where Qdrant runs
    VISION_MODEL,  # Step 1 model
)  # End of settings
from chat import chat_stream  # Chat answers (no image)
from embed_server import embedding_url  # Processor-only Ollama copy for guideline searches
from judge import model_capabilities, warm_up  # What the judge model can do; loading it ahead of time
from pipeline import check_image  # The whole check
from report import build_report  # Makes the PDF report

app = FastAPI(title="Aida")  # Create the web app
check_lock = threading.Lock()  # Only one check at a time: the AI models share the graphics card
STATIC_DIR = Path(__file__).parent / "static"  # Folder that holds the web page


def get_ready():  # Runs once in the background when the server starts, so the first question is fast
    embedding_url()  # Start the processor-only Ollama copy for guideline searches
    with check_lock:  # Don't compete with a check that started right away
        warm_up()  # Load the judge and pre-read the chat instructions


threading.Thread(target=get_ready, daemon=True).start()  # Start getting ready without delaying the web page


def event(kind, **data):  # Builds one line of the live progress stream
    return json.dumps({"type": kind, **data}) + "\n"  # One JSON object per line


@app.get("/")  # The home page
def index():  # Sends the web page to the browser
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-store"})  # The whole UI is in this one file; never cached, so updates show up on reload


@app.get("/upload")
def upload_page():
    return FileResponse(STATIC_DIR / "upload.html", headers={"Cache-Control": "no-store"})


@app.post("/api/documents")
def upload_document(file: UploadFile = File(...), replace: bool = Form(False)):
    try:
        name = source_name(file.filename)
        data = read_upload(file.file)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        file.file.close()
    events = queue.SimpleQueue()
    def work():
        try:
            for item in ingest_document(data, name, replace, collection=UPLOAD_COLLECTION):
                events.put(item)
        except Exception as exc:
            events.put({'type': 'error', 'message': str(exc)})
        finally:
            events.put(None)
    threading.Thread(target=work, daemon=True).start()
    def stream():
        yield event('stage', message='Waiting for ingestion')
        while True:
            item = events.get()
            if item is None:
                return
            yield json.dumps(item) + '\n'
    return StreamingResponse(stream(), media_type='application/x-ndjson')


@app.get("/api/status")  # Health check shown at the top of the page
def status():  # Reports whether Ollama, the models and the guidelines are ready
    info = {  # Defaults (assume nothing works until checked)
        "vision_model": VISION_MODEL, "judge_model": JUDGE_MODEL, "embedding_model": EMBEDDING_MODEL,  # Model names
        "collection": COLLECTION, "ollama": False, "missing_models": [], "qdrant": False, "passages": 0,  # Services
        "judge_tools": False, "device": None, "busy": check_lock.locked(),  # Features and activity
        "context_limit_chars": CHAT_CONTEXT_CHARS, "context_limit_tokens": CHAT_CONTEXT_LIMIT,  # Memory limit per chat (for the usage bar)
    }  # End of defaults
    try:  # Ollama might not be running
        client = ollama.Client(host=OLLAMA_URL)  # Connection to Ollama
        installed = {m.model for m in client.list().models}  # Downloaded models, e.g. "gpt-oss:20b"
        installed |= {name.removesuffix(":latest") for name in installed}  # "nomic-embed-text:latest" also counts as "nomic-embed-text"
        info["ollama"] = True  # Ollama answered
        info["missing_models"] = [m for m in (VISION_MODEL, JUDGE_MODEL, EMBEDDING_MODEL) if m not in installed]  # Models still to download
        info["judge_tools"] = "tools" in model_capabilities()  # Can the judge search the guidelines?
        loaded = client.ps().models  # Models currently in memory
        if loaded:  # Something is loaded
            info["device"] = "GPU" if any((m.size_vram or 0) > 0 for m in loaded) else "CPU"  # Memory on the graphics card means GPU
    except Exception:  # Could not reach Ollama
        pass  # Keep the defaults
    try:  # Qdrant might not be running
        info["passages"] = guidelines.passage_count()  # Number of guideline passages
        info["qdrant"] = True  # Qdrant answered
    except Exception:  # Could not reach Qdrant, or the collection doesn't exist
        pass  # Keep the defaults
    return info  # Send it to the browser


def read_image(image):  # Checks an uploaded image and returns its bytes
    suffix = Path(image.filename or "").suffix.lower()  # File extension, e.g. ".png"
    if suffix not in IMAGE_TYPES:  # Not a supported image
        raise HTTPException(400, f"Unsupported file type. Upload {', '.join(IMAGE_TYPES)}.")  # Refuse it
    data = image.file.read()  # The image itself
    if len(data) > MAX_IMAGE_MB * 1024 * 1024:  # Too big
        raise HTTPException(400, f"The image is larger than {MAX_IMAGE_MB} MB.")  # Refuse it
    return data  # The image


def stream_events(make_events):  # Runs a check or chat answer (one at a time) and sends its events as lines of JSON
    def stream():  # Produces the live progress
        if not check_lock.acquire(blocking=False):  # Another check or answer is running
            yield event("queued")  # Tell the page it has to wait
            check_lock.acquire()  # Wait for our turn
        try:  # Always release the lock, even if something fails
            for kind, payload in make_events():  # Each event
                if isinstance(payload, dict):  # "search" and "result" are already dictionaries
                    yield event(kind, **payload)  # Send their fields
                elif kind in ("stage", "tokens"):  # Simple values
                    yield event(kind, value=payload)  # Send the value
                else:  # Text: description, thinking, answer text, warning
                    yield event(kind, text=payload)  # Send the text
            yield event("done")  # Finished
        except Exception as e:  # Something went wrong (e.g. Ollama or Qdrant not running)
            yield event("error", message=str(e))  # Show the error on the page
        finally:  # Whatever happened
            check_lock.release()  # Let the next one run

    return StreamingResponse(stream(), media_type="application/x-ndjson")  # Send lines as they are produced


@app.post("/api/chat")  # Send a chat message, with or without an ad image
def chat(message: str = Form(""), history: str = Form("[]"), image: UploadFile | None = File(None)):  # Text, earlier messages (JSON), optional image
    try:  # The history must be valid JSON
        earlier = json.loads(history)  # [{"role": "user" | "assistant", "content": "..."}]
    except json.JSONDecodeError:  # Broken history
        earlier = []  # Start without it
    used = sum(len(str(m.get("content", ""))) for m in earlier if isinstance(m, dict)) + len(message)  # This chat's memory use, in characters
    if used > CHAT_CONTEXT_CHARS:  # The chat is full: the AI couldn't re-read all of it
        raise HTTPException(409, "This chat has reached its length limit. Start a new chat to continue.")  # The page shows this
    if image is not None and image.filename:  # An image is attached: check it against the ASC guidelines
        data = read_image(image)  # The image
        return stream_events(lambda: check_image(data, note=message))  # The full check; the message is passed on as context
    if not message.strip():  # No image and no text
        raise HTTPException(400, "Type a message or attach an image.")  # Nothing to do
    return stream_events(lambda: chat_stream(message, earlier if isinstance(earlier, list) else []))  # A chat answer


@app.post("/api/check")  # Check one ad image (without chat; used by scripts)
def check(image: UploadFile = File(...)):  # Receives the uploaded image; streams progress and the result back
    data = read_image(image)  # The image
    return stream_events(lambda: check_image(data))  # The full check


@app.post("/api/report")  # Make the PDF report of a finished check
def report(image: UploadFile = File(...), data: str = Form(...)):  # The image again (the server never stores it) and the result as JSON text
    try:  # The data must be valid JSON
        info = json.loads(data)  # {"result": {...}, "decision": "...", "notes": "...", "file_name": "..."}
    except json.JSONDecodeError:  # Broken data
        raise HTTPException(400, "Invalid report data.")  # Refuse it
    pdf = build_report(  # Build the PDF
        info.get("result") or {},  # The check result
        image.file.read(),  # The ad image
        file_name=str(info.get("file_name") or image.filename or ""),  # Its file name
        decision=str(info.get("decision") or ""),  # Approve / Revise / Reject
        notes=str(info.get("notes") or ""),  # Reviewer notes
    )  # End of report
    stem = re.sub(r"[^\w-]+", "-", Path(image.filename or "ad").stem).strip("-") or "ad"  # Safe version of the image name, e.g. "golden-lager"
    name = f"ASC-prescreen-{stem}-{datetime.now():%Y-%m-%d}.pdf"  # e.g. ASC-prescreen-golden-lager-2026-10-23.pdf
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"'})  # Download it


if __name__ == "__main__":  # Only run when this file is executed directly
    print(f"Open http://127.0.0.1:{PORT} in your browser")  # Tell the user where to go
    uvicorn.run(app, host="127.0.0.1", port=PORT)  # Only this computer can reach it (127.0.0.1)
