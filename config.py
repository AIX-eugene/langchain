import os  # Standard library module for reading environment variables
from pathlib import Path  # Standard library module for working with file paths

from dotenv import load_dotenv  # Loads settings from the .env file into environment variables

load_dotenv()  # Read .env (if it exists) so os.getenv can see our settings

ROOT = Path(__file__).parent  # The project folder
PROMPTS = ROOT / "prompts"  # Folder with the AI instructions and rule summaries

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")  # Where Ollama runs; this PC by default
VISION_MODEL = os.getenv("VISION_MODEL", "minicpm-v:8b")  # Step 1: the model that looks at the image and describes it
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gpt-oss:20b")  # Step 2: the model that checks the description against the ASC rules
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")  # Turns search text into vectors (must match how the guidelines were stored)
JUDGE_NUM_CTX = int(os.getenv("JUDGE_NUM_CTX", "16384"))  # How much text the judge can read at once. Its instructions alone are ~8,000 tokens; bigger values no longer fit a 16 GB GPU and run much slower
VISION_NUM_CTX = int(os.getenv("VISION_NUM_CTX", "8192"))  # How much text the vision model can read and write at once

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")  # The Qdrant server (the same one n8n uses)
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or None  # Only needed if your Qdrant server has a key
COLLECTION = os.getenv("QDRANT_COLLECTION", "asc_guidelines")  # Collection holding the ASC Guidebook passages
TOP_K = int(os.getenv("TOP_K", "3"))  # Passages returned per guideline search (n8n used 3)
MAX_SEARCHES = int(os.getenv("MAX_SEARCHES", "5"))  # Most guideline searches the judge may make per image (its instructions say 2 to 5)

PORT = int(os.getenv("PORT", "8000"))  # Port for the web page: http://127.0.0.1:<PORT>
IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}  # Accepted image files (same as the n8n form)
MAX_IMAGE_MB = int(os.getenv("MAX_IMAGE_MB", "20"))  # Largest image accepted, in megabytes


def read_prompt(name):  # Reads one instruction file from the prompts folder
    return (PROMPTS / name).read_text(encoding="utf-8")  # Its full text
