# Local Assistant

A private AI chat assistant that answers questions about **your own documents**:
PDFs, Excel spreadsheets, CSV files and text files. Everything runs **on your own computer**.
No internet connection, account or API key is needed once it's set up, and your documents
never leave the machine.

You can use it in two ways:

- **In your web browser**: a chat page with document upload (`server.py`)
- **In a terminal window**: a simple text chat (`main.py`)

---

## Contents

1. [What it does (in plain words)](#1-what-it-does-in-plain-words)
2. [Words you'll see in this guide](#2-words-youll-see-in-this-guide)
3. [What you need](#3-what-you-need)
4. [Installation, step by step](#4-installation-step-by-step)
5. [Everyday use](#5-everyday-use)
6. [How it works inside](#6-how-it-works-inside)
7. [The files in this project](#7-the-files-in-this-project)
8. [Settings](#8-settings)
9. [Using other AI models](#9-using-other-ai-models)
10. [Common developer tasks](#10-common-developer-tasks)
11. [Troubleshooting](#11-troubleshooting)
12. [Known limits](#12-known-limits)
13. [Web API reference](#13-web-api-reference)

---

## 1. What it does (in plain words)

1. You put files in the `documents` folder, or drag them into the web page.
2. The program reads them, cuts them into small pieces and saves those pieces in a
   **searchable database** on your computer.
3. When you ask a question, it finds the pieces that best match your question and gives them
   to an **AI model** running on your computer, which writes the answer.
4. For spreadsheets it can do more: the AI can **filter, count and group every row**, so
   questions like *"How many billboards were vacant in January?"* get exact answers.
5. Every answer shows **which file (and page, sheet or row)** the information came from.

---

## 2. Words you'll see in this guide

| Word | What it means |
|---|---|
| **AI model / LLM** | The "brain" that reads text and writes answers. This project uses **gpt-oss:20b**. |
| **Ollama** | A free program that runs AI models on your computer. Our code talks to it. |
| **Embedding** | A list of numbers that represents the *meaning* of a piece of text. Texts with similar meaning get similar numbers. Made by the model **nomic-embed-text**. |
| **Vector database** | A database that stores embeddings and can quickly find "the texts closest in meaning to this question". This project uses **Qdrant**. |
| **Chunk** | One small piece of a document: one spreadsheet row, or about 1,200 characters of a PDF or text file. |
| **Ingest** | Reading your files, cutting them into chunks and saving them in the database. |
| **RAG** (Retrieval-Augmented Generation) | "Search first, then answer": find the relevant chunks, then let the AI answer using them. This is what the project does. |
| **Tool** | A function the AI is allowed to call. Here: `query_table`, which filters and counts spreadsheet rows. |
| **LangChain** | A Python library that connects the pieces (AI model, database, prompts, tools). |
| **Terminal** | A window where you type commands. On Windows, use **PowerShell**: press Start, type `PowerShell` and press Enter. |
| **uv** | A tool that installs Python and this project's libraries, and runs the project. |
| **`.env` file** | A small text file with settings (which model to use, and so on). Optional. |

---

## 3. What you need

**Computer**

| | Minimum | Recommended |
|---|---|---|
| Operating system | Windows 10/11 (also works on macOS and Linux) | Windows 11 |
| Memory (RAM) | 16 GB | 32 GB |
| Graphics card | Not required (but slow without one) | NVIDIA with **16 GB** of memory or more |
| Free disk space | 20 GB | 30 GB |

> **About the graphics card (GPU):** the AI runs **much faster** on an NVIDIA graphics card.
> Without one, it uses the processor (CPU), which works but is slow. If you have an NVIDIA card,
> its **driver must be version 531 or newer** (see [Troubleshooting](#the-ai-runs-on-cpu-instead-of-gpu)).

**Programs** (installation steps are below)

- **Ollama**: runs the AI models
- **uv**: installs Python and the project's libraries

An internet connection is only needed **during installation**, to download the programs and models.

---

## 4. Installation, step by step

Do these steps **once** per computer. Every command goes into **PowerShell**. Type it (or paste it
with right-click), then press **Enter**.

### Step 1: Install Ollama

1. Go to **https://ollama.com/download** and download the Windows version.
2. Run the installer and click through it.
3. Ollama now runs in the background. You'll see a small llama icon near the clock, bottom right.
4. Check that it works. Open PowerShell and run:

   ```powershell
   ollama --version
   ```

   You should see something like `ollama version is 0.40.4`.

### Step 2: Download the two AI models

These are large downloads, so it may take a while.

```powershell
ollama pull gpt-oss:20b
```

This is the chat model (about **13 GB**).

```powershell
ollama pull nomic-embed-text
```

This is the embedding model (about **270 MB**).

Check that both are there:

```powershell
ollama list
```

You should see both `gpt-oss:20b` and `nomic-embed-text` in the list.

### Step 3: Install uv

Run this in PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then **close PowerShell and open it again**, so it picks up the new program. Check it:

```powershell
uv --version
```

> You do **not** need to install Python yourself. uv downloads the right version (3.11) automatically.

### Step 4: Get the project folder

Copy the project folder (the one containing this `README.md`) to the computer, for example to
`C:\Users\<you>\Documents\Langchain`.

Then open PowerShell **inside that folder**:

```powershell
cd "C:\Users\<you>\Documents\Langchain"
```

> **Tip:** in File Explorer, open the folder, click the address bar, type `powershell` and press
> Enter. A PowerShell window opens already in that folder.

**Every command from here on must be run inside the project folder.**

### Step 5: Install the project's libraries

```powershell
uv sync
```

This creates a hidden `.venv` folder containing Python and all the libraries listed in
`pyproject.toml`, at the exact versions recorded in `uv.lock`. It takes a minute or two the first time.

### Step 6 (optional): Create your settings file

The project works **without** a settings file. You only need one to change something, such as using
a different model or running Ollama on another computer.

```powershell
copy .env.example .env
```

Then open `.env` in Notepad and edit it. Every setting is explained in [Settings](#8-settings).

### Step 7: Add your documents

Put your files in the **`documents`** folder inside the project. Create the folder if it doesn't exist.

Supported file types:

| Type | Extension | Notes |
|---|---|---|
| PDF | `.pdf` | Must contain real text. Scanned images of pages can't be read. |
| Excel | `.xlsx` | Every sheet is read. The **first row must be the column titles**. Old `.xls` files: open them in Excel and save as `.xlsx`. |
| CSV | `.csv` | First row must be the column titles. |
| Text | `.txt`, `.md` | |

Subfolders are fine.

### Step 8: Load the documents into the database

```powershell
uv run ingest.py
```

You'll see progress like this:

```
Adding documents\sites.xlsx: 1408 chunks
  32/1408 (2%)
  64/1408 (4%)
  ...
Done. 1408 chunks added; the database now holds 1408 chunks.
```

> **Let it finish.** Large files can take several minutes, especially without a graphics card.
> If it's interrupted, just run it again. Finished files are skipped, and unfinished ones are redone.

### Step 9: Start the web interface

```powershell
uv run server.py
```

When you see `Open http://127.0.0.1:8000 in your browser`, open that address in any browser.

**Leave this PowerShell window open** while you use the app. To stop it, click the window and press
**Ctrl + C**.

That's it. Ask a question to try it out.

---

## 5. Everyday use

### Starting the app

1. Make sure Ollama is running (llama icon near the clock). If not, start **Ollama** from the Start menu.
2. Open PowerShell in the project folder.
3. Run `uv run server.py` and open **http://127.0.0.1:8000**.

### The web page

```
┌───────────────────────┬──────────────────────────────────────────┐
│ Local Assistant       │                                          │
│ [+ New chat]          │   Your question                [bubble]  │
│                       │                                          │
│ KNOWLEDGE BASE    (2) │   ▸ Thought process   (click to open)    │
│ ┌───────────────────┐ │   ▦ Checked sites.xlsx · Type ...        │
│ │  Add documents    │ │   The answer, with tables and lists...   │
│ └───────────────────┘ │   [sites.xlsx, sheet Sheet1]  ← sources  │
│ XLSX sites.xlsx       │                                          │
│ PDF  report.pdf       │                                          │
│                       │                                          │
│ ● Ollama connected    │                                          │
│ Running on      GPU   │                                          │
│ Spreadsheet tool  On  │ ┌──────────────────────────────────────┐ │
│ Indexed chunks 1,408  │ │ Message Local Assistant…          [↑]│ │
└───────────────────────┴─┴──────────────────────────────────────┴─┘
```

| Part | What it does |
|---|---|
| **New chat** | Clears the conversation and starts fresh. |
| **Add documents** | Click, or drag files onto it. They're saved to the `documents` folder and added to the database automatically. |
| **Trash icon** (hover over a file) | Deletes the file from the folder **and** from the database. |
| **Thought process** | The AI's reasoning before it answered. Click to expand. |
| **Checked …** | Shows when the AI queried a spreadsheet, and how many rows matched. |
| **Source tags** | Which files the answer used. |
| **Status panel** | Whether Ollama is reachable, which models are used, whether the AI runs on **GPU** (fast) or **CPU** (slow, shown in orange), whether the **spreadsheet tool** is on (it depends on the model, see [section 9](#9-using-other-ai-models)), and how many chunks are stored. |
| **Stop button** (■) | Appears while an answer is being written. Click it to cancel. |

Keyboard: **Enter** sends, **Shift + Enter** starts a new line.

### Good questions to ask

| Kind of question | Example |
|---|---|
| Look up one thing | *What is the status of site NAN0105?* |
| Categories | *What types of sites are there, and how many of each?* |
| Filter and list | *List the billboards that were VACANT on 2025-01-24 in Pasay.* |
| Count | *How many sites does Metro Devco operate?* |
| Follow-up | *Which of those are in Malibay?* (it remembers the conversation) |
| Text documents | *Summarize the main points of report.pdf.* |

### Adding documents without the web page

1. Copy the files into the `documents` folder.
2. **Stop the server** (Ctrl + C), because only one program can use the database at a time.
3. Run `uv run ingest.py`.
4. Start the server again with `uv run server.py`.

`ingest.py` keeps the database in sync with the folder:

| You did this | `ingest.py` does this |
|---|---|
| Added a new file | Adds it |
| Changed a file | Replaces its old chunks with new ones |
| Didn't touch a file | Skips it (fast) |
| Deleted a file | Removes its chunks from the database |

### Terminal chat (no browser)

```powershell
uv run main.py
```

Type a question and press Enter. Type `exit` to quit. Close the web server first, because the
two can't run at the same time.

---

## 6. How it works inside

### The big picture

```
                  ADDING DOCUMENTS (ingest.py, or upload in the web page)
  ┌────────────┐   read & cut    ┌─────────┐   make embeddings  ┌──────────────┐
  │ documents/ │ ──────────────▶ │ chunks  │ ─────────────────▶ │   Qdrant     │
  │ pdf, xlsx… │   (ingest.py)   │         │ (nomic-embed-text) │ qdrant_data/ │
  └────────────┘                 └─────────┘                    └──────┬───────┘
                                                                       │
                  ASKING A QUESTION (server.py or main.py)             │ search
  ┌──────────┐   question   ┌───────────────────────────────────┐      │
  │   You    │ ───────────▶ │ 1. search(): best-matching chunks │◀─────┘
  └──────────┘              │ 2. overview of every spreadsheet  │
       ▲                    │ 3. prompt = rules + overview      │
       │                    │      + chunks + chat history      │
       │                    └──────────────┬────────────────────┘
       │                                   ▼
       │                    ┌───────────────────────────────────┐   query_table()
       │   streamed answer  │  gpt-oss:20b (running in Ollama)  │ ◀──────────────▶ every row of
       └─────────────────── │  may call the spreadsheet tool    │                  the spreadsheets
                            └───────────────────────────────────┘
```

### What happens when you ask a question

1. **Search** (`db.search`) finds the chunks that best match your question in two ways:
   - **Exact codes:** words that mix letters and digits (like `NAN0105`) are looked up word for
     word, and those rows come first.
   - **Meaning:** the question is turned into an embedding, and Qdrant returns the closest chunks.
   - The top 8 (`TOP_K`) are kept.
2. **Spreadsheet overview** (`tables.overview`) summarizes every spreadsheet: each column, and its
   most common values with counts. This lets the AI know what columns and categories exist.
3. **Prompt** (`rag.prompt`) combines the instructions, the overview, the chunks and the last few
   messages of the conversation.
4. **The AI answers** (`rag.answer_stream`). If the question needs many rows ("how many", "list
   all"), the AI calls the **`query_table`** tool instead of guessing. The tool filters, counts
   and groups the **full** spreadsheet and gives the result back to the AI. This can happen up to
   4 times per question.
5. The answer is **streamed** (sent word by word) to the browser or terminal, along with the
   sources and any spreadsheet checks.

### How files are cut into chunks

| File type | How it's cut | Why |
|---|---|---|
| Excel / CSV | **One chunk per row.** Each chunk starts with `File: … \| Sheet: … \| Row N`, followed by `Column: value` pairs. | A row is never cut in half, and every chunk makes sense on its own. |
| PDF | One document per page, then cut into pieces of about 1,200 characters, overlapping by 200. | Keeps the page number for sources. The overlap stops sentences from being lost at the cut. |
| Text / Markdown | Pieces of about 1,200 characters, overlapping by 200. | |

Spreadsheet clean-up done while reading:

- **Dates:** `2024-03-01 00:00:00` becomes `2024-03-01`.
- **Duplicate column names** get the column on their left added, e.g. `Status (2024-03-01)`.
- **Blank column titles** become `Column Q` (using the column letter).
- **Merged cells:** the value is copied into every cell of the merged area.
- **Empty rows and columns** are skipped.
- **Category counts** treat different spellings as one: `Streamer`, `streamer` and `STREAMER` are
  counted together.

### How the database stays correct

- Every chunk is labeled with its file name and a **fingerprint** (`file_hash`) of the file's contents.
- `ingest.py` compares fingerprints. If a file's stored chunks match its current fingerprint and
  count, the file is skipped. Otherwise its old chunks are deleted and it's added again.
- If you change *how* files are read (the code in `ingest.py`), increase `PIPELINE_VERSION` at the
  top of `ingest.py`. Every file is then re-added automatically on the next run.

---

## 7. The files in this project

```
Langchain/
├── documents/        ← YOUR FILES go here
├── qdrant_data/      ← the database (created automatically, do not edit)
├── static/
│   └── index.html    ← the web page (HTML, CSS and JavaScript in one file)
├── server.py         ← the web server: serves the page and handles chat, upload and delete
├── main.py           ← the terminal chat
├── ingest.py         ← reads files, cuts them into chunks, stores them in the database
├── db.py             ← database helpers: open Qdrant, search, delete, count
├── rag.py            ← the AI part: model settings, prompt, answering loop
├── tables.py         ← spreadsheet overview and the query_table tool
├── .env.example      ← example settings (copy to .env to use)
├── pyproject.toml    ← list of required libraries
├── uv.lock           ← exact library versions (managed by uv, don't edit)
└── .python-version   ← Python version (3.11)
```

Every Python file has a comment on each line explaining what it does. Read them in this order:

1. **`db.py`**: how the database is opened and searched
2. **`ingest.py`**: how files become chunks
3. **`tables.py`**: how spreadsheets are summarized and queried
4. **`rag.py`**: how the prompt is built and the AI answers
5. **`server.py`**: how the web page talks to all of the above
6. **`static/index.html`**: the page itself

### Who uses what

```
server.py ─┬─▶ rag.py ─┬─▶ tables.py ─▶ ingest.py ─▶ db.py
main.py  ──┘           └─▶ db.py
ingest.py (run on its own) ─▶ db.py
```

### Main libraries

| Library | Used for |
|---|---|
| `langchain` / `langchain-core` | Prompts, messages, tools |
| `langchain-ollama` | Talking to Ollama (chat and embeddings) |
| `langchain-qdrant`, `qdrant-client` | The vector database |
| `langchain-text-splitters` | Cutting long text into chunks |
| `openpyxl` | Reading Excel files |
| `pypdf` | Reading PDF files |
| `fastapi`, `uvicorn`, `python-multipart` | The web server and file uploads |
| `python-dotenv` | Reading the `.env` settings file |

---

## 8. Settings

All settings are optional. To change one, copy `.env.example` to `.env`, edit the value and restart the app.

| Setting | Default | What it does |
|---|---|---|
| `OLLAMA_MODEL` | `gpt-oss:20b` | The chat model. Must be downloaded with `ollama pull`. See [Using other AI models](#9-using-other-ai-models). |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Where Ollama runs. Change it to use another computer's Ollama (see [below](#use-an-ai-model-on-another-computer)). |
| `OLLAMA_NUM_CTX` | `16384` | How much text (in tokens) the AI can read at once. Ollama's own default (4096) is too small and silently cuts off documents. |
| `TOP_K` | `8` | How many chunks are given to the AI per question. |
| `EMBEDDING_MODEL` | `nomic-embed-text` | The model that makes embeddings. **If you change it, delete `qdrant_data` and run `ingest.py` again.** |
| `QDRANT_COLLECTION` | `documents` | Name of the table inside the database. |
| `QDRANT_PATH` | `qdrant_data` | Folder where the database is stored. |
| `PORT` | `8000` | Web page address: `http://127.0.0.1:<PORT>`. |
| `QDRANT_URL` / `QDRANT_API_KEY` | (empty) | Use a separate Qdrant server instead of the folder (see [below](#run-the-web-page-and-the-terminal-chat-at-the-same-time)). |

---

## 9. Using other AI models

The project uses **two** models, and each can be swapped:

| Model | Job | Default | Setting |
|---|---|---|---|
| **Chat model** | Reads your question and the documents, and writes the answer | `gpt-oss:20b` | `OLLAMA_MODEL` |
| **Embedding model** | Turns text into numbers so the database can search by meaning | `nomic-embed-text` | `EMBEDDING_MODEL` |

### 9.1 Switch to another Ollama chat model (no code changes)

Any chat model from **https://ollama.com/library** works.

1. **Download the model** (replace the name with the one you want):

   ```powershell
   ollama pull qwen3:14b
   ```

2. **Check what it can do:**

   ```powershell
   ollama show qwen3:14b
   ```

   Look at the **Capabilities** section:

   | Capability | What it means here | If the model doesn't have it |
   |---|---|---|
   | `completion` | It can chat | It can't be used as the chat model at all |
   | `tools` | It can use the **spreadsheet tool**, giving exact counts and lists over every row | Spreadsheet answers come only from the column summary and a few matching rows, so counts and lists may be incomplete |
   | `thinking` | It reasons before answering, shown as **Thought process** in the chat | No Thought process section, otherwise works the same |

3. **Tell the project to use it.** Create a `.env` file if you don't have one
   (`copy .env.example .env`), open it in Notepad and change:

   ```
   OLLAMA_MODEL=qwen3:14b
   ```

4. **Restart the app.** Stop it with Ctrl + C, then `uv run server.py`.

5. **Check the sidebar:** **Chat model** shows the new name, and **Spreadsheet tool** shows
   **On** (supports tools) or **Off** in orange (no tool support).

You **don't** need to run `ingest.py` again, because the database doesn't depend on the chat model.

> **The code adapts automatically.** When the app starts, `rag.model_capabilities()` asks Ollama
> what the model supports. It only turns on "thinking" and the spreadsheet tool if the model has
> them. Without this check, models without those features would fail with errors like
> `does not support thinking`.

#### Which model should I pick?

The whole model should fit in your graphics card's memory (VRAM), with a little room to spare.
If it doesn't fit, it still works, but slowly, because part of it runs on the processor.

| Your GPU memory | Models to try | Notes |
|---|---|---|
| No GPU / under 8 GB | `qwen3:4b`, `llama3.2:3b` | Small and fast, less accurate |
| 8 GB | `qwen3:8b`, `llama3.1:8b` | Good everyday choice; both support tools |
| 12 GB | `qwen3:14b` | Supports tools and thinking |
| 16 GB or more | `gpt-oss:20b` (default) | Supports tools and thinking |
| 24 GB or more | `qwen3:32b` | More accurate; slower |

Model names and sizes change over time, so always confirm with `ollama show <model>` (step 2).
For spreadsheet work, **choose a model with `tools`**.

> **Context size:** `OLLAMA_NUM_CTX` (default 16384) must not be larger than the model supports.
> `ollama show` lists it as **context length**. Most current models support 32768 or more.

### 9.2 Switch the embedding model

The embedding model decides how well the search finds relevant passages.

| Model | Size | Good for |
|---|---|---|
| `nomic-embed-text` (default) | 270 MB | English documents; fast |
| `mxbai-embed-large` | 670 MB | English; often slightly more accurate |
| `bge-m3` | 1.2 GB | **Multiple languages**, e.g. documents mixing English and Filipino |

Steps:

1. Download it, for example `ollama pull bge-m3`.
2. Set `EMBEDDING_MODEL=bge-m3` in `.env`.
3. Stop the app and **delete the `qdrant_data` folder**. This step is required: vectors from
   different embedding models can't be mixed, and the database would reject the new ones.
4. Run `uv run ingest.py` to rebuild the database.
5. Start the app again.

> `db.py` adds the special prefixes `search_document:` and `search_query:` only for `nomic`
> models, because those models were trained to expect them. Other models get plain text.

### 9.3 Use a model on another computer

See [Use an AI model on another computer](#use-an-ai-model-on-another-computer) below. It works
with any Ollama model.

### 9.4 Use a non-Ollama model (LM Studio, OpenAI, Claude, Gemini…)

This needs a **small code change** in `rag.py`, because the project talks to Ollama by default.

> **Privacy warning:** cloud models (OpenAI, Anthropic Claude, Google Gemini) send your questions
> **and the matching parts of your documents** to that company's servers, and they need a paid
> API key. Local servers like LM Studio, llama.cpp and vLLM keep everything on your computer.

**Example: any OpenAI-compatible server** (LM Studio, llama.cpp server, vLLM, or OpenAI itself)

1. Install the connector:

   ```powershell
   uv add langchain-openai
   ```

2. In `rag.py`, replace the body of `get_llm()` and make `model_capabilities()` report tool support:

   ```python
   def model_capabilities():  # This server isn't Ollama, so state what the model supports
       return {"completion", "tools"}  # Remove "tools" if the model can't call tools

   def get_llm():  # Creates the chat model client
       from langchain_openai import ChatOpenAI  # Connector for OpenAI-style servers
       return ChatOpenAI(
           model=os.getenv("OPENAI_MODEL"),  # e.g. the model name shown in LM Studio
           base_url=os.getenv("OPENAI_BASE_URL"),  # LM Studio: http://localhost:1234/v1 ; OpenAI: leave empty
           api_key=os.getenv("OPENAI_API_KEY", "not-needed"),  # Local servers usually don't check it
       )
   ```

3. Add the settings to `.env`:

   ```
   OPENAI_MODEL=<model name>
   OPENAI_BASE_URL=http://localhost:1234/v1
   OPENAI_API_KEY=<your key, only for cloud services>
   ```

**Example: Anthropic Claude.** Same idea, with `uv add langchain-anthropic`:

```python
def get_llm():
    from langchain_anthropic import ChatAnthropic
    return ChatAnthropic(model="claude-sonnet-5-5", max_tokens=4096)  # Reads ANTHROPIC_API_KEY from .env
```

Notes for non-Ollama models:

- The embedding model can stay on Ollama. Only the chat model changes.
- The sidebar's **Running on** line only works for Ollama models, so it will show `Idle`.
- **Never commit `.env`** (it holds your API key). It's already listed in `.gitignore`.

---

## 10. Common developer tasks

### Use a different AI model

See [Using other AI models](#9-using-other-ai-models).

### Change the AI's instructions

Edit the `prompt` text in `rag.py`.

### Support a new file type

1. Add the extension to `EXTENSIONS` in `ingest.py`.
2. Add a branch in `load_file()` that returns a list of `Document(page_content=..., metadata={"source": str(path)})`.
3. Add the extension to the `accept="..."` list of the file input in `static/index.html`.
4. Increase `PIPELINE_VERSION` in `ingest.py`, then run `uv run ingest.py`.

### Start the database over from scratch

1. Stop the server.
2. Delete the `qdrant_data` folder.
3. Run `uv run ingest.py`.

### Use an AI model on another computer

On the computer **with** the model:

1. Set a Windows environment variable `OLLAMA_HOST` = `0.0.0.0`, then restart Ollama.
2. Allow port 11434 through its firewall. In PowerShell **as administrator**:

   ```powershell
   New-NetFirewallRule -DisplayName "Ollama" -Direction Inbound -Protocol TCP -LocalPort 11434 -Action Allow
   ```

3. Find its IP address with `ipconfig`, for example `192.168.1.50`.

On **this** computer, set `OLLAMA_BASE_URL=http://192.168.1.50:11434` in `.env`.

> Only do this on a network you trust: anyone on it can use that model.

### Run the web page and the terminal chat at the same time

By default the database is a folder that only **one program** can open at a time. To share it,
run Qdrant as a server with Docker:

```powershell
docker run -d -p 6333:6333 -v qdrant_storage:/qdrant/storage qdrant/qdrant
```

Then set `QDRANT_URL=http://localhost:6333` in `.env` and run `uv run ingest.py` once to fill it.

### Add or update a library

```powershell
uv add <library-name>
```

This updates `pyproject.toml` and `uv.lock` for you. Don't edit `uv.lock` by hand.

---

## 11. Troubleshooting

### "The database folder 'qdrant_data' is already in use by another program"

Only one of `server.py`, `main.py` and `ingest.py` can run at a time. Close the other one: type
`exit` in the terminal chat, or press **Ctrl + C** in the window running the server or ingest.

If you can't find that window, this lists the running copies:

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Select-Object ProcessId, CommandLine
```

Stop one by its number with `Stop-Process -Id <number>`.

### The status says "Ollama not running", or answers fail with a connection error

Start **Ollama** from the Start menu and wait a few seconds. Check it with `ollama list`.

### "model not found"

Download the missing model with `ollama pull gpt-oss:20b` or `ollama pull nomic-embed-text`.

### The AI runs on CPU instead of GPU

The sidebar shows **Running on: CPU** in orange, and answers are slow.

1. Check your NVIDIA driver version:

   ```powershell
   nvidia-smi
   ```

2. If the **Driver Version** is lower than **531**, update it:
   1. Go to **nvidia.com/drivers** and pick your card. For Quadro / RTX cards, choose the "RTX / Quadro" series.
   2. Download the newest driver and choose **Express** install.
   3. Restart the computer.
3. Ask a question, then run `ollama ps`. The **PROCESSOR** column should say `GPU`.

> Older cards (Pascal generation, e.g. Quadro P5200 or GTX 10xx) are supported up to the
> **R580 / 580.x** drivers.

### The sidebar says "Spreadsheet tool: Off"

The chat model you chose can't use tools, so spreadsheet counts and lists may be incomplete.
Switch to a model whose `ollama show <model>` output lists `tools` (see [section 9.1](#91-switch-to-another-ollama-chat-model-no-code-changes)).
It also shows **Off** if Ollama wasn't running when the app started: start Ollama, then restart the app.

### After changing the embedding model, adding documents fails

Vectors from different embedding models can't be mixed. Stop the app, delete the `qdrant_data`
folder and run `uv run ingest.py` again.

### `ingest.py` seems stuck

Watch the progress percentage. Without a GPU, about 1,400 spreadsheet rows can take 10 minutes or
more. If it was interrupted, run it again: it continues with the unfinished files.

### A PDF gives no answers

It's probably a scanned PDF (pictures of pages, with no real text). `ingest.py` prints
`Skipped (no text found)` for those. Run it through a text-recognition (OCR) tool first.

### Spreadsheet answers use the wrong column names

The first row of each sheet must contain the column titles. If your sheet has a title or logo above
the header row, delete those rows in Excel.

### Port 8000 is already in use

Set `PORT=8001` (or another number) in `.env`, then open `http://127.0.0.1:8001`.

---

## 12. Known limits

- **One program at a time** uses the database (unless you use the Qdrant server; see above).
- **While a large upload is being added**, questions wait until it finishes.
- **Chats are not saved.** Reloading the page or clicking *New chat* clears the conversation.
- **Spreadsheet filters match text *inside* a cell.** Filtering Type for `Banner` also matches
  `Column Banner`. Ask for the exact value if that matters.
- **Duplicate rows are kept.** Identical rows in a spreadsheet are stored and counted separately.
- **Typos in the data are not corrected.** `Unidentify` and `Undentify` are counted as two
  different values. Fix them in the source file.
- **Number columns can't be added up yet.** The tool counts rows; it doesn't sum or average values.
- **Scanned PDFs and old `.xls` files** are not supported (see Troubleshooting).

---

## 13. Web API reference

`server.py` only accepts connections from this computer (`127.0.0.1`).

| Method | Address | What it does | Sends back |
|---|---|---|---|
| `GET` | `/` | The web page | HTML |
| `GET` | `/api/status` | Health check | `{chat_model, embedding_model, chunks, ollama, device, tools}` |
| `GET` | `/api/documents` | List the files in `documents/` | `[{name, size}]` |
| `POST` | `/api/upload` | Upload one or more files (form field `files`) and add them to the database | `{files, chunks}` |
| `DELETE` | `/api/documents/{name}` | Delete a file and its chunks | `{deleted}` |
| `POST` | `/api/chat` | Ask a question. Body: `{message, history: [{role, content}]}` | A stream of JSON lines (see below) |

`/api/chat` sends one JSON object per line while the answer is being made:

| `type` | Other fields | Meaning |
|---|---|---|
| `sources` | `sources: [..]` | Files used for this answer |
| `thinking` | `text` | A piece of the AI's reasoning |
| `tool` | `label`, `summary` | A spreadsheet query that was run |
| `token` | `text` | A piece of the answer |
| `done` | | The answer is complete |
| `error` | `message` | Something went wrong |

Example test from PowerShell (with the server running):

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/status
```

---

## Privacy

- The AI models, the database and your documents all stay on this computer.
- The web server only accepts connections from this computer.
- The web page loads nothing from the internet.
- The internet is only used during installation, and when Ollama checks for its own updates.
