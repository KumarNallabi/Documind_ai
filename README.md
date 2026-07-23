# DocuMind AI

Upload PDFs and Markdown docs, ask questions in plain English, get answers
that are **grounded only in your files** — every claim carries a citation
(filename + page number) sourced from the retrieved chunk's stored metadata,
never invented by the model. If nothing relevant is found, the app returns
exactly `I cannot find this in the documents.` — enforced in code via a
similarity threshold, not left to the LLM's judgment.

## Tech stack actually used

This build follows a simplified stack requested for this project, which
**substitutes** a few pieces from a more elaborate original spec. Substitutions
are called out below so nothing is a silent surprise.

| Layer | Used | Notes |
|---|---|---|
| Backend | Django (plain views + JSON, no DRF) | |
| Database | MongoDB via `mongoengine` | **All** data — users, tokens, documents, chunks, conversations, messages — lives in MongoDB. Django's SQL `DATABASES` setting is only present because Django's core framework requires one to boot; nothing in the app uses it. |
| Vector search | Brute-force cosine similarity in Python (`numpy`), scoped by owner/document at query time | *Substitution:* not MongoDB Atlas Vector Search. This is intentional for MVP scale (fine into the tens of thousands of chunks) and keeps the whole stack runnable against any MongoDB instance, including a free-tier one. The retrieval function (`chat/retrieval.py`) has a single entry point (`retrieve()`), so swapping in `$vectorSearch` or FAISS/HNSW later doesn't touch any caller. |
| Async processing | Python `threading` (one background thread per upload) + frontend polling every 1.5s | *Substitution:* not Celery + Redis + Channels/SSE-push. You asked for a trimmed stack (Django + Mongo + Groq + vanilla JS only), so background work runs in-process instead of a separate worker queue, and status updates reach the browser via polling instead of a push channel. The pipeline steps themselves (`documents/processing.py`) are unchanged from what a Celery task would run — swapping this out later is a small, contained change if you outgrow single-process throughput. |
| Streaming chat responses | Server-Sent-Events-style streaming over a plain `fetch()` + `StreamingHttpResponse` | Not Django Channels/WebSockets — a normal HTTP streaming response is enough for one-directional token streaming and needs no extra infrastructure. |
| Embeddings | `sentence-transformers` (`all-MiniLM-L6-v2`), run locally | Groq does not currently serve an embeddings endpoint, so embeddings are generated locally — free, private, and fast enough on CPU at MVP scale. Swappable via `documents/embeddings.py`. |
| LLM | Groq (`llama-3.3-70b-versatile` by default) | Swappable via `chat/llm.py`. |
| Frontend | Plain HTML + CSS + JS, served by Django templates/staticfiles | No React/build step, per your request. |
| Auth | Custom bearer-token auth backed by MongoDB (not Django's built-in SQL-based auth) | Roles: `admin`, `standard`, `viewer`. |

## RAG algorithm, briefly

1. **Chunking** (`documents/chunking.py`): recursive, structure-aware splitting
   (paragraph → sentence → hard word-boundary fallback), 500 tokens / 50 token
   overlap by default, configurable via `.env`. Chunks never span a page
   (PDF) or heading section (Markdown) boundary, so citations stay exact.
2. **Embedding**: each chunk is embedded once at ingest time and stored with
   `document_id`, `filename`, `page_number`, `chunk_index`, `owner_id`.
3. **Retrieval** (`chat/retrieval.py`):
   - Embed the question with the same model.
   - Score every chunk owned by the requesting user (optionally narrowed to
     selected documents) by cosine similarity.
   - Take a generous candidate pool by raw similarity, then re-rank with
     **Maximal Marginal Relevance (MMR)** so the final top-K isn't just K
     near-duplicate slices of the same paragraph — this is the standard fix
     for redundant retrieval in production RAG systems.
   - Apply a **hard minimum-similarity threshold** to the best-scoring chunk.
     If nothing clears it, retrieval returns nothing and the view returns the
     refusal message **without calling the LLM at all**.
4. **Generation** (`chat/llm.py`): the system prompt explicitly restricts the
   model to the retrieved context and forbids outside knowledge. Citations
   shown to the user are built from the chunks' stored metadata, never
   parsed out of the model's free-text answer.

## Project layout

```
documind_ai/
├── manage.py
├── requirements.txt
├── .env.example
├── documind/          # Django project settings/urls
├── core/               # Mongo connection bootstrap, auth decorators, tiny CORS middleware
├── accounts/           # User/AuthToken/SharedDocumentAccess models + register/login/me views
├── documents/          # Document/Chunk models, parsing, chunking, embeddings, upload pipeline
├── chat/                # Conversation/Message models, retrieval (MMR), Groq streaming, views
├── templates/index.html
└── static/css/styles.css, static/js/api.js, static/js/app.js
```

## Setup

### 1. Prerequisites
- Python 3.11+
- A running MongoDB instance (local `mongod`, Docker, or MongoDB Atlas). No
  Redis is needed with this build's simplified async stack.
- A [Groq API key](https://console.groq.com/keys).

### 2. Install

```bash
cd documind_ai
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

The first Groq chat request and the first document upload will each trigger
a one-time model download in the background (Groq client is lightweight;
`sentence-transformers` downloads ~90MB for `all-MiniLM-L6-v2` on first use).

### 3. Configure

```bash
cp .env.example .env
```

Edit `.env`:
- `MONGO_URI` / `MONGO_DB_NAME` — point at your MongoDB instance. If you
  just want to click around without installing MongoDB, set
  `MONGO_USE_MOCK=True` to run against an in-memory mock (data does not
  persist across restarts — fine for a demo, not for real use).
- `GROQ_API_KEY` — required for chat answers to work at all. Uploads and the
  library screen work without it; only the "ask a question" step needs it.

### 4. Run

```bash
python manage.py runserver
```

Open `http://localhost:8000`. Register an account (pick a role — `standard`
is the normal case), then:

1. **Library** — drag a `.pdf` or `.md` file into the drop zone. Watch it move
   through Uploading → Parsing → Chunking → Embedding → Ready in the
   "Processing now" rail (polled every 1.5s).
2. **Chat** — once a document shows "ready" in the left rail, ask a question.
   The answer streams in token-by-token; when it finishes, one or more
   `⌷ filename · p.N · chunk NN` citation stubs fade in — click one to open
   the Source Preview panel with the exact excerpt highlighted.
3. **Voice** — once an answer finishes streaming, a small `🔊 Listen` control
   appears next to its citation stubs. Click it to have the browser read the
   answer aloud (uses the built-in Web Speech API — no API key, nothing sent
   over the network); click again (now labeled `◼ Stop`) to stop. It's
   deliberately left off the refusal state, which stays icon-free by design.
   Starting a new question, or logging out, stops any playback in progress.
   Voice availability depends on the browser (all modern desktop/mobile
   browsers support it; the button simply doesn't render if unsupported).
4. Ask something the documents don't cover and you should see the quiet,
   colorless refusal state: `I cannot find this in the documents.`

### 5. Run the tests

The two behaviors most likely to silently break are covered explicitly:

```bash
MONGO_USE_MOCK=True python manage.py test
```

This runs against an in-memory MongoDB mock (`mongomock`), so no real
database is needed to test:
- `chat/tests.py` — a user never retrieves another user's chunks; the
  similarity threshold correctly short-circuits low-relevance queries to a
  refusal and lets high-relevance ones through.
- `documents/tests.py` — the chunker never lets a chunk span a page
  boundary, and correctly splits/retains page numbers on long pages.

## Roles

- **Admin** — sees and manages every user's documents; can retry/delete/rename
  anything.
- **Standard user** — full control of their own documents and chat history;
  can share a document read-only with another user by username
  (`POST /api/documents/<id>/share/`).
- **Viewer** — read-only access to documents shared with them (no upload UI
  exposed for this role's typical use, though the API doesn't hard-block it —
  add that restriction if you need it enforced server-side for your use case).

## Known limitations / next steps for production

- Background processing runs in-process via Python threads. This is fine for
  a single Django process; move `documents/processing.py`'s pipeline into a
  real task queue (Celery + Redis, or RQ) before running multiple workers or
  processing large batches.
- Retrieval is a brute-force scan over a user's chunks. Swap
  `chat/retrieval.retrieve()`'s internals for MongoDB Atlas `$vectorSearch`
  or a FAISS/HNSW index once a single user's corpus grows large (tens of
  thousands+ chunks).
- Auth tokens don't expire. Add TTL/refresh if this goes further than a demo.
- No rate limiting on the Groq-backed `/api/chat/ask/` endpoint.
