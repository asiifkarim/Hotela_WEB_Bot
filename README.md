# Hotela Public Chatbot

Hotela is a knowledge-grounded visitor chatbot for a hotel and restaurant
management product. It answers questions from a reviewed static knowledge base,
supports a React chat widget, and exposes a FastAPI backend with streaming chat,
lead capture, health, and handoff endpoints.

The application does not scrape websites at runtime and does not access private
hotel, restaurant, customer, or owner-dashboard data.

## What the project solves

- Gives visitors concise answers about Hotela features, plans, support, and
  documented limitations.
- Uses vector retrieval, BM25 re-ranking, and a grounding prompt to keep
  generated answers tied to the knowledge base.
- Provides a deterministic grounded fallback when the LLM is unavailable.
- Keeps contact details out of ordinary answers unless a visitor asks for
  contact or support information.
- Offers a reusable React widget and a standalone local demo.

## Key features

- FastAPI backend with Server-Sent Events (SSE) chat responses.
- Local Hugging Face sentence-transformer embeddings.
- Persistent Chroma vector store.
- Hybrid vector/BM25 retrieval with similarity thresholds and de-duplication.
- Gemini generation with bounded calls, retries, and provider error handling.
- Grounding and prompt-injection guards.
- SQLite persistence for conversations, unanswered questions, and leads.
- Optional SMTP notification for submitted leads.
- React + TypeScript + Vite widget with Markdown rendering.
- Knowledge-base validation, index building, health checks, and retrieval
  evaluation scripts.

## Technology stack

### Backend

- Python 3.11+
- FastAPI and Uvicorn
- Pydantic Settings
- ChromaDB
- SQLAlchemy with SQLite
- Google Gemini API (`google-genai`)
- Sentence Transformers
- PyYAML and tiktoken
- Pytest

### Frontend

- React
- TypeScript
- Vite
- `react-markdown` and `remark-gfm`
- `lucide-react`

## Repository structure

```text
.
├── backend/
│   ├── app/                 FastAPI app, chat, RAG, LLM, database, leads
│   ├── eval/                Evaluation questions, baseline, and runner
│   ├── scripts/             KB validation, index build, and health check
│   ├── tests/               Backend tests
│   ├── .env.example         Safe configuration template
│   └── requirements.txt     Python dependencies
├── frontend/
│   ├── src/                 React widget and local demo entry points
│   ├── index.html           Vite demo page
│   ├── package.json         Frontend dependencies and scripts
│   └── vite.config.ts       Widget library build configuration
├── kb/
│   ├── *.md                 Canonical visitor-facing KB documents
│   ├── plans.json           Canonical plan/pricing data
│   └── archive/             Superseded KB material kept for provenance
├── scripts/                 Root-level maintenance wrappers
├── data/                    Local SQLite runtime data (ignored)
├── requirements.txt         Root-level compatibility dependency file
└── package.json             Root-level convenience scripts
```

`backend/chroma_db/` is generated local vector-store data and is ignored by
Git. It can be rebuilt from `kb/` when needed.

## Prerequisites

- Windows PowerShell, macOS, or Linux
- Python 3.11 or newer
- Node.js 18 or newer and npm
- A Gemini API key for live LLM generation
- Internet access on first run to download the embedding model

The application can still serve grounded fallback answers when Gemini is
unavailable, but live generation and multilingual response quality require a
working Gemini configuration.

## Installation

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Install frontend dependencies:

```powershell
cd frontend
npm install
cd ..
```

## Environment configuration

Create the local backend environment file:

```powershell
Copy-Item backend\.env.example backend\.env
```

Set the real key in `backend\.env`:

```env
GEMINI_API_KEY=your_gemini_api_key_here
```

Never commit `backend/.env`, `.env`, or any other file containing credentials.
The checked-in [backend/.env.example](backend/.env.example) contains
placeholders only.

Important defaults include:

```env
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.5-flash-lite
EMBEDDING_PROVIDER=huggingface
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
CHROMA_PERSIST_DIR=./chroma_db
TOP_K=6
MIN_SIMILARITY=0.35
```

The relative Chroma path is resolved under `backend/`, so the default store is
`backend/chroma_db/`.

## Build and validate the knowledge base

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe backend\scripts\validate_kb.py
.\.venv\Scripts\python.exe backend\scripts\build_index.py
```

The validator checks front matter, canonical topics, plan data, TODO/CONFLICT
markers, and duplicate content. The index builder recreates the
`hotela_kb` Chroma collection from canonical files in `kb/` and `kb/plans.json`.
Run both commands after changing KB content.

## Run the backend

From the repository root:

```powershell
$env:PYTHONPATH="backend"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

The first startup may take time while the local embedding model loads.

Useful checks from another terminal:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/health -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:8000/api/kb/version -UseBasicParsing
```

## Run the frontend

From the repository root:

```powershell
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

Open [http://127.0.0.1:5173/](http://127.0.0.1:5173/) in a browser. The demo
uses `VITE_API_URL` when supplied; otherwise it targets port 8000 on the
current hostname.

To build the embeddable widget:

```powershell
cd frontend
npm run build
```

The generated `frontend/dist/` directory is local build output and is ignored.

## API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Reports configuration, embeddings, vector store, and provider health |
| GET | `/api/kb/version` | Reports current/indexed KB versions and chunk count |
| POST | `/api/chat` | Guarded SSE chat endpoint |
| POST | `/api/leads` | Consent-required lead capture |
| POST | `/api/handoff` | Returns configured contact options |

Example chat request:

```powershell
$body = @{
  session_id = "local-demo"
  message = "What is Hotela?"
  history = @()
} | ConvertTo-Json -Compress

Invoke-WebRequest `
  -Uri http://127.0.0.1:8000/api/chat `
  -Method Post `
  -ContentType "application/json" `
  -Body $body `
  -UseBasicParsing
```

The response is Server-Sent Events containing `status`, `sources`, `token`,
`action`, `done`, or `error` events.

## Database and runtime data

The default SQLite database is `data/hotela.db`. It stores conversations,
unanswered questions, and submitted leads. The database is local runtime data
and is ignored by Git.

The Chroma vector store is generated under `backend/chroma_db/` and contains
embeddings for the indexed KB. If it is missing or stale, run the KB build
command above.

## Tests and evaluation

Run all backend tests:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
```

Run a retrieval evaluation without generation:

```powershell
$env:PYTHONPATH="backend"
.\.venv\Scripts\python.exe backend\eval\run_eval.py --no-generation
```

The evaluation uses `backend/eval/questions.yaml` and compares results with
`backend/eval/baseline.json`. Do not update the baseline unless the behavior
change is intentional and reviewed.

Root convenience commands are also available through `package.json`. Activate
the project environment before using them so `python` resolves to the
environment containing the backend dependencies.

## Example questions

- `What is Hotela?`
- `Does Hotela work for both hotels and restaurants?`
- `What are the Hotela plans?`
- `How can I contact Hotela?`
- `Is there a free trial?`

## Screenshots

No public screenshots are included in this repository yet.

## Known limitations

- Gemini availability, quotas, model access, and network latency depend on the
  configured Google account and API key.
- The embedding model is downloaded locally and increases first-start time and
  disk usage.
- The default persistence layer is SQLite and is intended for a small
  deployment, not a horizontally scaled production database.
- There are currently no dedicated frontend unit or end-to-end tests.
- The chatbot can only answer facts present in the reviewed KB.

## Future improvements

- Add frontend unit and browser-level tests.
- Add production database and secret-management integrations.
- Add observability dashboards and request tracing.
- Add a deployment configuration for a managed API and static frontend host.
- Add automated KB freshness and source-review workflows.

## Contributing

1. Create a feature branch.
2. Keep canonical KB content under `kb/`; do not edit archived material for
   runtime behavior.
3. Run KB validation, backend tests, and the frontend build.
4. Review `git diff` and `git diff --check`.
5. Open a pull request describing behavior changes and verification results.

## License

No license has been selected for this repository yet. Do not reuse the code
outside the permissions granted by the repository owner until a license is
added.
