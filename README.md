# MedResearch AI

An AI medical research assistant that answers clinical questions from **real
scientific literature** (PubMed + your own uploaded PDFs) using
Retrieval-Augmented Generation — with **every claim traceable to a source**.

![status](https://img.shields.io/badge/build-passing-brightgreen)

## What it does

Ask a medical research question → the system searches PubMed, indexes the
papers, retrieves the most relevant passages, and has Claude answer **using only
that evidence**, with inline `[n]` citations that resolve to real PMIDs. Upload
your own PDFs to make them searchable the same way. A LangGraph multi-agent
workflow handles deep "research this topic" queries with a fact-checking loop.

## Architecture

```
Next.js (TS + Tailwind)  ──JWT──▶  FastAPI  ──▶  PostgreSQL (system of record)
   login / dashboard /                │      ──▶  ChromaDB   (vector index)
   search / chat / docs               │      ──▶  PubMed E-utilities
   + citations panel                  │      ──▶  Claude API
```

Full design rationale — the dual-store pattern, layered backend, RAG and agent
workflows, deployment topology — is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Quick start (Docker — one command)

```bash
cp backend/.env.example .env          # then set ANTHROPIC_API_KEY (+ PUBMED_EMAIL)
docker compose up --build
```

- Frontend → http://localhost:3000
- API docs → http://localhost:8000/docs

The backend applies database migrations automatically on startup and bakes the
embedding model into its image, so the first request is fast.

## Local development

```bash
# Infrastructure
docker compose up -d postgres chromadb

# Backend
cd backend
uv sync
cp .env.example .env                  # set ANTHROPIC_API_KEY
uv run alembic upgrade head
uv run uvicorn app.main:app --reload  # http://localhost:8000/docs

# Frontend
cd frontend
npm install
npm run dev                           # http://localhost:3000
```

## Testing

```bash
cd backend && uv run pytest           # 45 tests (needs postgres running)
cd frontend && npm run build          # type-check + production build
```

## Tech stack

| Layer | Choice |
|---|---|
| Backend | FastAPI, async SQLAlchemy 2, Pydantic v2, Python 3.12 |
| Database | PostgreSQL 16 (Alembic migrations) |
| Vector store | ChromaDB (cosine, model-versioned collection) |
| Embeddings | sentence-transformers (MiniLM; PubMedBERT-swappable) |
| LLM | Claude API |
| Agents | LangGraph (5-agent graph with fact-check loop) |
| Frontend | Next.js 16, TypeScript, Tailwind v4 |
| Infra | Docker, docker-compose; Azure Container Apps ready |

## Key features

- **Citation-grounded RAG** — retrieval floor + prompt contract + post-hoc
  citation validation; refuses to answer when evidence is insufficient.
- **Multi-agent research** — Search → Retrieval → Summarize → Fact-Check → Report.
- **PDF upload** — extract → chunk → embed → searchable, with a status lifecycle.
- **Auth + history** — JWT accounts, persisted chat sessions and search history.

## Security notes

- Secrets come from the environment only; `.env` is gitignored, never baked into
  images. Production uses a managed secret store (see ARCHITECTURE.md §7).
- Passwords are bcrypt-hashed; JWTs are short-lived HS256.
- PubMed and each retrieved paper carry their own licenses — see
  [.licenses/pubmed_database_LICENSE.txt](.licenses/pubmed_database_LICENSE.txt).
