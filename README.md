# ASC Ad Pre-screen

A private AI tool that checks **advertising images** (billboards and other out-of-home ads) against
the **Ad Standards Council (ASC) Philippines** guidelines, before they go to official ASC screening.

You upload an ad image. The tool tells you whether it looks **compliant** or **non-compliant**.
For every problem it shows the ASC rule, the evidence from the ad and how to fix it.

Everything runs **on your own computer**: no internet, account or API key is needed once it's set up,
and images never leave the machine.

> **This is a pre-screen, not an ASC decision.** A person must always review the result.

This is the Python version of the n8n workflow **"ASC v3"**. It does the same steps with the same
prompts, the same rule summaries and the same Qdrant guidelines (see [How it maps to n8n](#how-it-maps-to-the-n8n-workflow)).

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
9. [Changing prompts, rules and models](#9-changing-prompts-rules-and-models)
10. [Troubleshooting](#10-troubleshooting)
11. [Known limits](#11-known-limits)
12. [Web API reference](#12-web-api-reference)

---

## 1. What it does (in plain words)

```
  ┌───────────┐   1. DESCRIBE    ┌──────────────┐   2. CHECK RULES    ┌──────────────┐   3. VERIFY    ┌──────────┐
  │ Ad image  │ ───────────────▶ │ Written      │ ──────────────────▶ │ AI verdict   │ ─────────────▶ │  Result  │
  │ (JPG/PNG) │  minicpm-v:8b    │ description  │  gpt-oss:20b reads  │ (JSON)       │  Python code   │  page    │
  └───────────┘  looks at the    │ of the ad    │  the ASC rules and  └──────────────┘  removes made- └──────────┘
                 image           └──────────────┘  searches the ASC                    up problems,
                                                   Guidebook in Qdrant                 adds missed
                                                                                       decency issues
```

1. **Describe:** a vision model (**minicpm-v:8b**) looks at the image and writes down everything it sees:
   all text, the product, claims, warnings and fine print, people, and other visuals.
2. **Check the rules:** a reasoning model (**gpt-oss:20b**) compares that description with the ASC rule
   checklist. Along the way it searches the **ASC Guidebook** (stored in Qdrant as `asc_guidelines`)
   for the exact rule wording.
3. **Verify:** Python code double-checks the AI's answer:
   - It **removes** "violations" the AI made up, such as rules for the wrong product type, a
     "missing" warning that is actually there, or evidence that isn't in the ad.
   - It **adds** decency problems the AI missed, such as revealing clothing or intimate poses.
   - It attaches a **plain-language explanation** of every ASC rule.
4. **Result:** you see the image next to the verdict and findings. You record your own decision
   (Approve / Revise / Reject) and download a **PDF report**.

---

## 2. Words you'll see in this guide

| Word | What it means |
|---|---|
| **ASC** | Ad Standards Council, the body that screens ads in the Philippines. Its rules are in the ASC Guidebook (Code of Ethics and Manual of Procedures). |
| **OOH** | Out-of-home advertising: billboards, posters, transit ads. Seen by everyone, so the decency rules are strict. |
| **AI model** | The "brain" that reads and writes. This tool uses two: a **vision model** that can see images, and a **judge model** that reasons about rules. |
| **Ollama** | A free program that runs AI models on your computer. |
| **Qdrant** | A database that finds text **by meaning**. It holds the ASC Guidebook, cut into ~1,000-character passages. |
| **Embedding** | A list of numbers representing the meaning of a text. Searching compares these numbers. Made by **nomic-embed-text**. |
| **Collection** | One "table" in Qdrant. Ours is called `asc_guidelines`. |
| **Tool** | A function the AI is allowed to call. Here: `asc_guidelines`, which searches the guidebook. |
| **Prompt** | The written instructions given to an AI model. Ours are in the `prompts` folder. |
| **Docker** | A program that runs other programs in "containers". Qdrant (and n8n) run in Docker. |
| **Terminal** | A window where you type commands. On Windows use **PowerShell**: press Start, type `PowerShell`, press Enter. |
| **uv** | A tool that installs Python and this project's libraries, and runs the project. |
| **n8n** | A visual workflow tool. The first version of this checker was an n8n workflow. |

---

## 3. What you need

**Computer**

| | Minimum | Recommended |
|---|---|---|
| Operating system | Windows 10/11 | Windows 11 |
| Memory (RAM) | 16 GB | 32 GB |
| Graphics card | NVIDIA with 8 GB (slow) | NVIDIA with **16 GB** or more |
| Free disk space | 30 GB | 40 GB |

> The graphics card matters a lot. Without one, a check can take 10 minutes or more. The NVIDIA
> driver must be **version 531 or newer** (see [Troubleshooting](#the-check-is-very-slow)).

**Programs** (installed in the steps below)

- **Ollama**: runs the AI models
- **Docker Desktop**: runs the Qdrant database (skip if you already run n8n with Qdrant)
- **uv**: installs Python and this project's libraries

The internet is only needed **during installation**.

---

## 4. Installation, step by step

Do this **once** per computer. Every command goes into **PowerShell**: type or paste it
(right-click pastes), then press **Enter**.

### Step 1: Install Ollama

1. Download it from **https://ollama.com/download** and run the installer.
2. A llama icon appears near the clock (bottom right), which means Ollama is running.
3. Check it:

   ```powershell
   ollama --version
   ```

### Step 2: Download the three AI models

```powershell
ollama pull minicpm-v:8b
```

The vision model that describes the image (about **5.5 GB**).

```powershell
ollama pull gpt-oss:20b
```

The judge model that checks the ASC rules (about **13 GB**).

```powershell
ollama pull nomic-embed-text
```

The search model for the guidebook (about **270 MB**).

Check that all three are listed:

```powershell
ollama list
```

### Step 3: Start the Qdrant database

> **Already using the n8n workflow?** Then Qdrant is already running with the guidelines loaded.
> Skip to Step 4.

1. Install **Docker Desktop** from **https://www.docker.com/products/docker-desktop** and start it.
2. Start Qdrant (this keeps its data in a Docker volume called `qdrant_storage`):

   ```powershell
   docker run -d --name qdrant --restart unless-stopped -p 6333:6333 -v qdrant_storage:/qdrant/storage qdrant/qdrant
   ```

3. Check it: open **http://localhost:6333/dashboard** in a browser. You should see the Qdrant dashboard.

### Step 4: Install uv

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Close PowerShell and open it again**, then check:

```powershell
uv --version
```

> You don't need to install Python yourself. uv downloads the right version automatically.

### Step 5: Get the project and install its libraries

1. Copy the project folder (the one with this `README.md`) to the computer.
2. Open PowerShell **in that folder**. Tip: in File Explorer, open the folder, click the address
   bar, type `powershell` and press Enter.
3. Install the libraries:

   ```powershell
   uv sync
   ```

**Every command from here on must be run inside the project folder.**

### Step 6: Load the ASC Guidebook into Qdrant

> **Skip this if the guidelines are already loaded** (for example by n8n). The web page's header
> shows **"Guidelines: 438 passages"** when they are.

You need the ASC Guidebook as a PDF with real text (not a scan). Then:

```powershell
uv run ingest_guidelines.py "C:\path\to\ASC Guidebook.pdf"
```

You'll see progress up to 100%. It takes a few minutes.

### Step 7: Start the app

```powershell
uv run server.py
```

When you see `Open http://127.0.0.1:8000 in your browser`, open that address.

**Leave this window open** while you use the app. Press **Ctrl + C** in it to stop.

### Step 8 (optional): Change settings

Everything works with the defaults. To change something (a model, a port…):

```powershell
copy .env.example .env
```

Then edit `.env` in Notepad and restart the app. All settings are explained in [Settings](#8-settings).

---

## 5. Everyday use

### Starting the app

1. Make sure **Ollama** (llama icon near the clock) and **Docker Desktop** are running.
2. Open PowerShell in the project folder and run `uv run server.py`.
3. Open **http://127.0.0.1:8000**.

The header shows what's ready:

| Chip | Meaning |
|---|---|
| **Ollama ready** | The AI models can run |
| **Guidelines: 438 passages** | Qdrant is reachable and the ASC Guidebook is loaded |
| **Running on GPU** | The models use the graphics card (fast). Orange **CPU** means slow |

If something is missing, a yellow **"Setup needed"** bar says exactly what to do.

### Checking an ad

1. **Drop the ad image** onto the left panel, or click it to choose a file (JPG or PNG).
2. Click **Check this ad**.
3. Watch the three steps: **Describe → Check rules → Verify**. A check takes **about 3 minutes**
   on a 16 GB graphics card. Meanwhile you can open:
   - **What the AI sees in the image**: the description, written live
   - **Guideline searches**: what the AI looked up in the ASC Guidebook, and what it found
   - **Thought process**: the judge's reasoning
4. **Read the result:**

   | Result | What you see |
   |---|---|
   | **✕ Non-compliant** | One card per problem: the problem, **what the ASC rule says** (blue box), **evidence** from the ad, **how to fix** it, and the ASC reference. Problems tagged *"Added by decency check"* were missed by the AI but found by the code. |
   | **✓ Compliant** | Why it passed, plus every check that was made (mandatory statements, claims, visuals, decency) |
   | **! Could not check** | The reason, e.g. the AI's answer wasn't readable. Just run it again. |

   **Removed by verification** (if shown) lists problems the AI raised that weren't backed by the
   image, for transparency.
5. **Review it yourself.** Compare the image with the findings, choose **Approve / Revise / Reject**,
   and add notes.
6. Click **Download PDF report** to keep a record. The PDF (A4) contains:
   - the ad image, the verdict and every finding, with the rule explanation, evidence and fix
   - your decision (ticked box) and notes, plus *Reviewed by* and *Date* lines to sign
   - an appendix with what the AI saw in the image, so anyone can see what the findings were based on

   It's saved to your Downloads folder as e.g. `ASC-prescreen-golden-lager-2026-10-23.pdf`.

> The decision and notes are **not saved** by the app. Download the PDF to keep them. Choose
> the decision and write the notes **before** clicking the button.
>
> Ctrl + P also prints the page (always in light colors), but the PDF report is the cleaner record.

### Checking from the terminal (no browser)

```powershell
uv run check.py "C:\path\to\ad.png"
```

This prints the description, the searches and the result, which is handy for testing. Stop the
web server first if both would run at the same time; they share the graphics card.

---

## 6. How it works inside

### Step by step

**Step 1: describe** (`vision.py`)
- Sends the image to **minicpm-v:8b** through Ollama, with two prompts:
  - `prompts/describe_system.md`: "describe only, in English, don't judge", taken from the n8n node.
  - `prompts/describe.md`: the 7 sections to fill in (ALL TEXT, PRODUCT, CLAIMS, WARNINGS AND FINE
    PRINT, PEOPLE, OTHER VISUALS, UNREADABLE). It insists on copying only text that is really in the image.
- The description is streamed to the page as it's written.

**Step 2: check the rules** (`judge.py`)
- Sends `prompts/judge.md` (the n8n AI Agent prompt, about 8,000 tokens) with the description
  filled in, to **gpt-oss:20b**.
- The prompt holds the full **ASC rule checklist** (G general, C claims, P price/promo, R category
  rules, plus the decency checklist D1–D6). It tells the AI to call the **`asc_guidelines`** tool 2 to
  5 times to confirm rule wording.
- Each search returns the **3 closest passages** from Qdrant (`guidelines.py`). Repeated searches are
  refused, and passages already shown aren't sent again, to keep the AI's memory from overflowing.
- The AI answers with **JSON**: the verdict, and either the violations (rule, evidence, problem, fix,
  rule explanation) or the checks that passed.

**Step 3: verify** (`checks.py`, the Python version of the n8n "Code in JavaScript" node)
1. **Finds the product category** in the description from keywords (beer → `R-ALC`, supplement → `R-SUPP`, …).
2. **Removes made-up violations:**
   - a category rule for a product type the ad doesn't show (e.g. milk rules on a beer ad)
   - "MISSING: …" when the statement **is** in the description
   - evidence whose words aren't in the description (needs 60% word overlap)
3. **Adds decency problems the AI missed**, by scanning the description for intimate contact
   (kissing, embracing, hands on hips…) and revealing clothing (bikini, shirtless, lingerie…). Under
   ASC Article I Section 4 and Annex 3, borderline decency counts as non-compliant for OOH.
4. **Attaches rule explanations** from `prompts/rules.json`: the plain-language summary of all 54
   ASC rule IDs (G-01…G-14, C-01…C-17, P-01…P-07, R-…). These are used first because they're always
   accurate; the AI's own summary is the fallback.
5. **Handles language problems:** if the vision model answered in Chinese (it sometimes does), the
   judge's English translation (`description_en`) is used. If there is none, the result is
   "Could not check" rather than an unchecked verdict.

### How it maps to the n8n workflow

| n8n node | Python |
|---|---|
| Upload Image (form) | `static/index.html` + `server.py` (`/api/check`) |
| Extract from File | Not needed: the browser shows the image itself |
| Analyze image (minicpm-v:8b) | `vision.py` |
| AI Agent + Ollama Chat Model (gpt-oss:20b, think) | `judge.py` |
| asc_guidelines (Qdrant, retrieve-as-tool, top 3) + Embeddings Ollama1 | `guidelines.py` |
| Code in JavaScript | `checks.py` + `prompts/rules.json` |
| Form (completion page) | The result panel in `static/index.html`, plus a downloadable PDF report (`report.py`) |
| On form submission (PDF) → Default Data Loader → Text Splitter → Qdrant Vector Store | `ingest_guidelines.py` |

Both versions use **the same Qdrant collection**, so n8n and this app can run side by side.

---

## 7. The files in this project

```
Langchain/
├── server.py              ← the web server: serves the page, runs checks, reports status
├── check.py               ← check one image from the terminal
├── pipeline.py            ← runs the three steps in order and reports progress
├── vision.py              ← step 1: describe the image (minicpm-v)
├── judge.py               ← step 2: check the rules (gpt-oss), with guideline searches
├── guidelines.py          ← search the asc_guidelines collection in Qdrant
├── checks.py              ← step 3: verify the AI's answer (port of the n8n code node)
├── report.py              ← makes the PDF report
├── ingest_guidelines.py   ← add a guideline PDF to Qdrant
├── config.py              ← all settings, read from .env
├── prompts/
│   ├── describe_system.md ← vision model: who it is (describe only, English only)
│   ├── describe.md        ← vision model: the 7 sections to write
│   ├── judge.md           ← judge model: the full ASC checklist and output format
│   └── rules.json         ← plain-language summary of every ASC rule ID
├── static/
│   └── index.html         ← the web page (HTML, CSS and JavaScript in one file)
├── archive/document-chat/ ← the previous version of this project (document Q&A), kept for reference
├── .env.example           ← example settings (copy to .env)
├── pyproject.toml         ← required libraries
└── uv.lock                ← exact library versions (managed by uv, don't edit)
```

Every Python file has a comment on each line explaining what it does. To learn the code, read in
this order: `config.py` → `vision.py` → `guidelines.py` → `judge.py` → `checks.py` → `pipeline.py` → `server.py`.

### Who uses what

```
server.py ──▶ report.py (PDF report)
server.py ─┐
check.py ──┴─▶ pipeline.py ─┬─▶ vision.py
                            ├─▶ judge.py ──▶ guidelines.py ──▶ Qdrant (asc_guidelines)
                            └─▶ checks.py ──▶ prompts/rules.json
ingest_guidelines.py ──▶ guidelines.py ──▶ Qdrant
```

---

## 8. Settings

All settings are optional. Copy `.env.example` to `.env`, edit it, and restart the app.

| Setting | Default | What it does |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Where Ollama runs. Use another computer's address to run the models there. |
| `VISION_MODEL` | `minicpm-v:8b` | Step 1 model (must be able to see images). |
| `JUDGE_MODEL` | `gpt-oss:20b` | Step 2 model. Should support **tools**, so it can search the guidelines. |
| `JUDGE_NUM_CTX` | `16384` | How much text the judge can hold. Its instructions are ~8,000 tokens and a full check peaks around 11,000–13,000. Larger values don't fit a 16 GB card and make checks **much** slower. |
| `VISION_NUM_CTX` | `8192` | How much text the vision model can hold. |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Search model. **Must be the model the guidelines were stored with.** |
| `QDRANT_URL` | `http://localhost:6333` | The Qdrant server. |
| `QDRANT_API_KEY` | (empty) | Only if your Qdrant server needs a key. |
| `QDRANT_COLLECTION` | `asc_guidelines` | The collection with the guidebook. |
| `TOP_K` | `3` | Passages returned per guideline search (n8n used 3). |
| `MAX_SEARCHES` | `5` | Most guideline searches per image. |
| `PORT` | `8000` | Web page address: `http://127.0.0.1:<PORT>`. |
| `MAX_IMAGE_MB` | `20` | Largest image accepted. |

---

## 9. Changing prompts, rules and models

### Change what the AI is told

The instructions are plain text files in `prompts/`. Edit them in any editor and restart the app.

| File | Change it to… |
|---|---|
| `describe.md` | ask the vision model to describe something more or differently |
| `judge.md` | change the ASC checklist, strictness or output format. It **must** keep the `{description}` placeholder, and the JSON output format that `checks.py` reads (`verdict`, `reasons`, `checks_passed`, …). |
| `rules.json` | change the plain-language rule summaries shown in the results |

> If you edit the prompts in n8n too, copy the changes here (or the other way round). The two
> versions don't sync automatically.

### Use different models

1. Download the model, e.g. `ollama pull llama3.2-vision:11b`.
2. Check what it can do with `ollama show <model>`:
   - **Vision model:** must list `vision`.
   - **Judge model:** should list `tools`, so it can search the guidelines. Without tools the
     header shows **"Judge can't search"**, and it relies only on the checklist in the prompt.
     `thinking` is optional.
3. Set `VISION_MODEL=` or `JUDGE_MODEL=` in `.env` and restart.

Sizes to keep in mind on a 16 GB card: the vision and judge models run **one after the other**,
so each must fit on its own. They don't need to fit together.

### Change the search model

The guidelines were stored with `nomic-embed-text`. To use another embedding model, you must
**reload the guidebook** with it: delete the `asc_guidelines` collection in the Qdrant dashboard
(http://localhost:6333/dashboard), set `EMBEDDING_MODEL=` in `.env`, and run `ingest_guidelines.py`
again. **Note:** n8n's Embeddings nodes would then need the same model.

### Add more guideline documents

```powershell
uv run ingest_guidelines.py "C:\path\to\another-guideline.pdf"
```

To replace a file you added before (after an update, for example), add `--replace` at the end.

---

## 10. Troubleshooting

### The yellow bar says "Setup needed"

It names the problem. The common ones:

| Message | Fix |
|---|---|
| Start **Ollama** | Start Ollama from the Start menu |
| Download the missing model(s) | Run the `ollama pull …` command shown |
| Start the **Qdrant** server | Open Docker Desktop and start the `qdrant` container (▶ button) |
| The collection is empty | Load the guidebook ([Step 6](#step-6-load-the-asc-guidebook-into-qdrant)) |

### The check is very slow

A normal check takes about 3 minutes on a 16 GB NVIDIA card.

1. Look at the header: **Running on CPU** (orange) means the graphics card isn't used. Run
   `nvidia-smi`; if the **Driver Version** is below 531, update the driver from
   **nvidia.com/drivers**, then restart the computer.
2. Run `ollama ps` during a check. If **PROCESSOR** shows a big CPU share (e.g. `30%/70% CPU/GPU`),
   the model doesn't fit in the card's memory:
   - Close other programs that use the graphics card (browsers with many tabs, games, 3D software).
   - Don't raise `JUDGE_NUM_CTX` above 16384.
3. Part of every check is loading the models: the vision model and the judge take turns on the
   graphics card, because both don't fit at once.

### "Could not check: The AI did not return valid JSON"

The judge's answer was cut off or badly formatted. Run the check again. If it keeps happening,
open **Thought process**. If the reasoning stops mid-sentence, the AI ran out of memory: lower
`MAX_SEARCHES` to 3.

### "The image description came back in another language"

minicpm-v sometimes answers in Chinese. Run the check again. If it keeps happening, try
`VISION_MODEL=llama3.2-vision:11b`.

### The result is clearly wrong

1. Open **What the AI sees in the image**. Most mistakes start here: the vision model misread
   small text or missed something. Higher-resolution images help.
2. Open **Guideline searches** to see which rules the AI looked up.
3. Adjust `prompts/describe.md` or `prompts/judge.md` if a mistake keeps repeating.

### Port 8000 is already in use

Set `PORT=8001` in `.env` and open `http://127.0.0.1:8001`.

---

## 11. Known limits

- **It's a pre-screen.** It can't replace ASC screening, and a person must review every result.
- **It only knows what the vision model sees.** Very small, blurry or stylized text may be
  misread or missed, which can cause false "missing statement" findings.
- **Documents can't be checked.** Claims that need proof (sales data for "No. 1", research for
  "best", permits, licenses) are noted as needing documents, not flagged as violations.
- **Images only:** JPG and PNG. No video, audio or multi-page PDFs.
- **One check at a time.** Others wait in line (the page says "Waiting for another check").
- **Decisions aren't saved.** Use **Download PDF report**.
- **The rules are from the ASC Guidebook of March 2019** (the version loaded in Qdrant and
  summarized in the prompts). Update both if ASC publishes changes.

---

## 12. Web API reference

The server only accepts connections from this computer (`127.0.0.1`).

| Method | Address | What it does |
|---|---|---|
| `GET` | `/` | The web page |
| `GET` | `/api/status` | Readiness: `{ollama, missing_models, qdrant, passages, judge_tools, device, busy, …}` |
| `POST` | `/api/check` | Check an image. Send it as form field `image` (JPG/PNG). Replies with a stream of JSON lines. |
| `POST` | `/api/report` | Make the PDF report. Form fields: `image` (the same image) and `data` (JSON: `{result, decision, notes, file_name}`). Replies with the PDF file. |

`/api/check` sends one JSON object per line:

| `type` | Fields | Meaning |
|---|---|---|
| `queued` | | Another check is running; this one waits |
| `stage` | `value`: `describe` / `judge` / `verify` | A new step started |
| `describe` | `text` | A piece of the image description |
| `thinking` | `text` | A piece of the judge's reasoning |
| `search` | `query`, `result` | A guideline search and the passages found |
| `tokens` | `value` | How full the judge's memory is |
| `result` | `result`, `reasons`, `checks_passed`, `approval_summary`, `removed_reasons`, `description`, `seconds`, … | The final result |
| `error` | `message` | Something went wrong |

Example from PowerShell:

```powershell
curl.exe -F "image=@C:\path\to\ad.png" http://127.0.0.1:8000/api/check
```

---

## Privacy

- Images are processed in memory and **never stored** by the app.
- The AI models, the guidelines and the web page all run on this computer. The page loads nothing
  from the internet.
- The internet is only used during installation, and when Ollama or Docker check for updates.
