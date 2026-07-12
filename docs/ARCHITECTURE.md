# MedResearch AI — System Architecture

An AI Medical Research Assistant that answers medical research questions from real
scientific literature (ten federated scholarly sources + user-uploaded PDFs) using
Retrieval-Augmented Generation, with every claim traceable to a source.

## Federated source layer (10 APIs)

Search fans out in parallel to ten free scholarly APIs, then deduplicates,
merges, and ranks the combined results before anything is stored:

```
query ─┬─► PubMed ──────────┐
       ├─► PubMed Central    │
       ├─► OpenAlex          │   asyncio.gather (parallel, per-source timeout,
       ├─► ClinicalTrials.gov│   failure-isolated: one source down ≠ search down)
       ├─► Europe PMC        │
       ├─► Crossref          ├─► DEDUP (canonical key: doi > pmid > src:id > title-hash)
       ├─► arXiv             │   MERGE (union sources, max citation_count, best abstract)
       ├─► bioRxiv           │   RANK  (Reciprocal Rank Fusion + citation bonus)
       ├─► medRxiv           │
       └─► openFDA ──────────┘─► upsert (Postgres, idempotent by dedup_key)
                                 └─► ingest → ChromaDB
```

- **Provider abstraction** (`services/sources/`): each API normalizes to one
  `SourceRecord` DTO, so dedup/merge/rank are source-agnostic. Adding a source is
  one new file + one line in the registry.
- **Dedup by `dedup_key`**, not PMID — most sources have no PMID (a DOI, an arXiv
  id, an NCT number, an FDA label id). The same paper found by five APIs collapses
  to one row; `sources` records all five for provenance.
- **Ranking** fuses each source's relevance order via RRF (tuning-free, standard)
  plus a log-scaled citation bonus, so highly-cited *and* multiply-agreed papers
  rise. Citation counts come mainly from OpenAlex / Crossref / Europe PMC.
- **bioRxiv/medRxiv** have no keyword-search API of their own; they're retrieved
  through Europe PMC's preprint index (`PUBLISHER:"bioRxiv"`), the standard route.
- **Provenance to the answer**: chunk metadata carries `source`/`sources`, so
  every RAG citation names which API(s) it came from — the "cite the source of
  every document" requirement, enforced end to end.
- **Failure isolation**: each source runs under a timeout and a catch-all; a 429
  or schema change drops that one source, never the whole search.

---

## 1. High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Next.js Frontend (TypeScript + Tailwind)       │
│   Login │ Dashboard │ Search │ Chat (+ citations panel) │ Docs │ History │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ HTTPS + JWT (Bearer)
┌───────────────────────────────▼─────────────────────────────────────────┐
│                            FastAPI Backend                              │
│                                                                         │
│  API layer (routers)      →  thin: validation, auth, HTTP concerns      │
│  Service layer            →  all business logic                         │
│  ┌──────────┬───────────┬──────────────┬───────────┬────────────────┐   │
│  │ PubMed   │ Ingestion │ Vector Search│ RAG       │ LangGraph      │   │
│  │ client   │ pipeline  │ (ChromaDB)   │ pipeline  │ agent workflow │   │
│  └──────────┴───────────┴──────────────┴───────────┴────────────────┘   │
│  Data layer (SQLAlchemy async + Alembic)                                │
└──────┬──────────────────────┬──────────────────────┬────────────────────┘
       │                      │                      │
┌──────▼──────┐        ┌──────▼──────┐        ┌──────▼──────────────┐
│ PostgreSQL  │        │  ChromaDB   │        │  External services  │
│ (metadata,  │        │ (embeddings,│        │  PubMed E-utilities │
│ users, chat,│        │  semantic   │        │  Claude API         │
│ citations)  │        │  search)    │        │                     │
└─────────────┘        └─────────────┘        └─────────────────────┘
```

### Why two databases?

This is the **dual-store pattern**, standard in RAG systems:

- **PostgreSQL is the system of record.** Everything durable and relational lives
  here: users, paper metadata, chunk text, chat history, citations. If ChromaDB is
  wiped, we can rebuild every vector from Postgres.
- **ChromaDB is a derived index.** It stores embeddings and answers one question
  fast: "which chunks are semantically closest to this query?" It is optimized for
  approximate nearest-neighbor search, which Postgres (without pgvector) is not.

**Alternative considered:** `pgvector` extension — one database, no sync problem.
Excellent choice in production. We use ChromaDB here because (a) the spec requires
it, (b) it teaches the more common industry pattern of a dedicated vector store,
and (c) swapping to pgvector later only touches one service class because vector
access is behind an interface.

**Tradeoff accepted:** two stores can drift. We mitigate by writing Postgres first
(source of truth), then Chroma, and storing the Chroma ID on each `paper_chunks`
row so reconciliation is always possible.

> **Operational note (learned in verification):** ingestion is idempotent by
> checking Postgres — if a paper already has `paper_chunks` rows, we skip
> re-embedding. That check *assumes the two stores share a lifecycle*. If you
> wipe one volume but not the other (e.g. a fresh ChromaDB against a Postgres
> volume left over from an earlier run), Postgres says "already ingested" and
> Chroma stays empty — searches then return nothing. Treat the `pgdata` and
> `chromadata` volumes as a unit: reset them together (`docker compose down -v`).
> A production hardening would be a `reconcile` job that re-embeds any
> `paper_chunks` row whose `chroma_id` is missing from the vector store.

---

## 2. Repository Layout (monorepo)

```
medical-research-assistant/
├── docs/
│   └── ARCHITECTURE.md          ← this file
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app factory + lifespan
│   │   ├── core/
│   │   │   ├── config.py        # pydantic-settings (all env config)
│   │   │   ├── logging.py       # structured logging setup
│   │   │   └── security.py      # JWT + password hashing
│   │   ├── db/
│   │   │   ├── base.py          # Declarative base, naming conventions
│   │   │   └── session.py       # async engine + session factory
│   │   ├── models/              # SQLAlchemy ORM models (1 file per aggregate)
│   │   ├── schemas/             # Pydantic request/response models
│   │   ├── api/
│   │   │   ├── deps.py          # dependency-injection providers
│   │   │   └── routes/          # auth, search, chat, documents, health
│   │   ├── services/            # business logic, no HTTP concerns
│   │   │   ├── pubmed.py        # NCBI E-utilities client
│   │   │   ├── chunking.py      # text cleaning + chunking
│   │   │   ├── embeddings.py    # embedding model wrapper
│   │   │   ├── vector_store.py  # ChromaDB access (only place Chroma appears)
│   │   │   ├── ingestion.py     # orchestrates chunk → embed → store
│   │   │   ├── rag.py           # retrieval + prompt + Claude + citations
│   │   │   └── pdf.py           # PDF text extraction
│   │   └── agents/
│   │       ├── state.py         # typed graph state
│   │       ├── nodes.py         # the 5 agent node functions
│   │       └── graph.py         # LangGraph wiring
│   ├── alembic/                 # migrations
│   ├── tests/
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── src/app/                 # Next.js App Router pages
│   ├── src/components/
│   ├── src/lib/                 # API client, auth helpers
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
└── README.md
```

### Why this layout (clean/layered architecture)

Requests flow **routes → services → models/stores**, never sideways or backwards:

- **Routes are thin.** They parse input, check auth, call one service method,
  shape the response. No business logic. Why: HTTP is an implementation detail;
  the same service is callable from an agent node, a CLI, or a background job.
- **Services own logic and are the only layer that touches external systems.**
  ChromaDB appears *only* in `vector_store.py`; PubMed *only* in `pubmed.py`.
  Why: when we swap ChromaDB for pgvector or Pinecone, one file changes.
- **Models vs. schemas are deliberately separate.** SQLAlchemy models describe
  storage; Pydantic schemas describe the API contract. Coupling them (one class
  for both) is a classic junior mistake — it leaks DB columns into API responses
  and makes migrations breaking API changes.

**Alternative considered:** full hexagonal architecture with repository
interfaces and domain entities. Overkill at this size — the service layer already
gives us the seams we need for testing and swapping infrastructure.

---

## 3. Database Design (PostgreSQL)

```
users ──────────┬──────────────────────────────────────────────┐
                │                                              │
                ▼                                              ▼
         chat_sessions ──► chat_messages ──► citations   search_history
                                                 │
                                                 ▼
papers ──► paper_chunks ◄──────────────── (chunk_id FK)
                ▲
documents ──────┘   (uploaded PDFs produce chunks too)
```

| Table | Purpose | Key design decisions |
|---|---|---|
| `users` | accounts | email unique, bcrypt password hash — never plaintext |
| `papers` | PubMed metadata | `pmid` unique; upsert on re-search (idempotent ingestion) |
| `documents` | uploaded PDFs | *added beyond spec* — uploads aren't papers; they have filenames, owners, processing status |
| `paper_chunks` | chunk text + position | stores the actual text (source of truth); `chroma_id` links to the vector; chunk belongs to *either* a paper or a document |
| `chat_sessions` | one conversation | title auto-generated from first question |
| `chat_messages` | turns in a session | role (user/assistant), content, ordered by created_at |
| `citations` | message → chunk links | this is what makes answers auditable: every `[n]` marker in an answer resolves to a real chunk with a real PMID |
| `search_history` | queries per user | powers the History page |

**Why `chat_sessions` + `chat_messages` instead of one `chat_history` table:**
a single table conflates two entities. Sessions have titles and are listed on the
dashboard; messages belong to sessions and are ordered. Normalizing them makes
"continue previous research session" a trivial query instead of a GROUP BY hack.

**Why citations are a table, not JSON in the message row:** referential
integrity. A citation row FK-references an actual chunk, which FK-references an
actual paper. The claim chain answer → chunk → paper is enforced by the database,
not by hoping the LLM formatted JSON correctly.

Migrations: **Alembic**, autogenerate + hand review. Schema changes are code
reviewed like any other code.

---

## 4. RAG Workflow

```
User question
   │
   ├─► (1) Embed question              — same model used at ingestion time
   ├─► (2) ChromaDB similarity search  — top-k (k≈8) by cosine distance
   ├─► (3) Filter & rank               — drop chunks below relevance threshold;
   │                                     dedupe by paper; keep best ≈5
   ├─► (4) Assemble context            — numbered blocks: [1] title/PMID + text
   ├─► (5) Claude with grounding prompt— "answer ONLY from sources, cite [n],
   │                                     say 'insufficient evidence' if unsure"
   └─► (6) Parse citations             — map [n] markers back to chunk IDs,
                                         persist to citations table
```

**Hallucination controls (defense in depth):**
1. *Retrieval floor* — if no chunk clears the similarity threshold, we say so
   instead of letting the model guess.
2. *Prompt contract* — system prompt forbids claims without a `[n]` marker.
3. *Post-hoc verification* — cited indices are validated against the context we
   actually sent; dangling citations are stripped.
4. *(Agent mode)* a dedicated fact-checking node re-reads the draft against the
   sources before the report is generated.

**Embedding model choice:** `sentence-transformers` running locally.
- Default: `all-MiniLM-L6-v2` (384-dim) — small, fast, good general quality.
- Configurable upgrade: `NeuML/pubmedbert-base-embeddings` (768-dim) — trained on
  biomedical text; noticeably better on medical vocabulary (e.g., knowing
  "myocardial infarction" ≈ "heart attack").
- **vs. OpenAI embeddings:** hosted embeddings are excellent but add API cost,
  latency, a second vendor key, and an outbound dependency for *every* search.
  Local embedding of short chunks is fast even on CPU. The model name is a config
  value; swapping is a one-line change (plus re-ingestion — embeddings from
  different models are not comparable, so we version the Chroma collection name
  by model).

**Chunking strategy:** recursive character splitting, ~1,200 chars with 200
overlap, splitting on paragraph → sentence → word boundaries in that order.
Abstracts (150–300 words) usually stay whole; PDF full text gets split. Overlap
exists so a sentence straddling a boundary is fully present in at least one
chunk. Every chunk carries metadata (pmid/document_id, title, journal, year,
chunk index) so search results are self-describing.

---

## 5. Multi-Agent Workflow (LangGraph)

For complex research questions, a single RAG pass is shallow. The agent graph
decomposes the work:

```
                    ┌────────────────┐
 user question ───► │  Search Agent  │  decides PubMed queries, fetches+ingests papers
                    └───────┬────────┘
                    ┌───────▼────────┐
                    │ Retrieval Agent│  vector search over fresh + existing corpus
                    └───────┬────────┘
                    ┌───────▼────────┐
                    │ Summarization  │  per-source evidence summaries w/ citations
                    └───────┬────────┘
                    ┌───────▼────────┐
                    │  Fact Checker  │  verifies each claim against source chunks
                    └───────┬────────┘     │ fails → loops back with corrections (max 2)
                    ┌───────▼────────┐
                    │ Report Agent   │  final structured, cited answer
                    └────────────────┘
```

- **State** is a single typed object (question, queries, retrieved chunks, draft
  summaries, verification verdicts, final report) that flows through the graph.
- **Why LangGraph over a hand-rolled pipeline:** the fact-checker needs to *loop
  back* on failure — that's a cyclic graph, which plain function composition
  doesn't express cleanly. LangGraph gives us cycles, checkpointing, and
  streaming of intermediate steps to the UI.
- **Why not "agents all the way down":** simple follow-up questions go through
  the plain RAG pipeline (cheaper, faster). The graph is for the heavyweight
  "research this topic" flow. Using a 5-agent graph to answer "what does PMID
  12345 say?" burns tokens for nothing.

---

## 6. Authentication

- Register → bcrypt-hash password → store.
- Login → verify hash → issue **JWT access token** (short-lived, HS256, secret
  from env/Key Vault).
- Protected routes depend on a `get_current_user` FastAPI dependency that
  validates the token and loads the user.
- Frontend stores the token and attaches `Authorization: Bearer` via a small API
  client; Next.js middleware redirects unauthenticated users to `/login`.

**Tradeoff noted:** hand-rolled JWT is required by the spec and worth learning,
but in a commercial product a managed provider (Clerk/Auth0/Entra) removes an
entire class of security bugs. We keep the auth surface minimal: no refresh-token
rotation, no password reset flow (documented as future work).

---

## 7. Deployment Architecture (Azure)

```
                      ┌───────────────────────────────┐
   Internet ────────► │  Azure Container Apps env     │
                      │  ┌──────────┐  ┌───────────┐  │
                      │  │ frontend │  │  backend  │  │
                      │  │ (Next.js)│─►│ (FastAPI) │  │
                      │  └──────────┘  └─────┬─────┘  │
                      │                ┌─────▼─────┐  │
                      │                │ chromadb  │  │ (internal ingress only,
                      │                │ +Azure File│ │  persistent volume)
                      │                └───────────┘  │
                      └───────────────┬───────────────┘
                                      │
                 ┌────────────────────┼────────────────────┐
                 ▼                    ▼                     ▼
        Azure Database for    Azure Key Vault      Azure Container
        PostgreSQL Flexible   (secrets: JWT key,   Registry (images)
        Server                Claude API key)
```

- **Container Apps** over AKS: serverless containers, scale-to-zero, no cluster
  ops — right-sized for a portfolio project that must still look production-real.
- **Secrets** never live in images or compose files: locally via `.env`
  (gitignored), in Azure via Key Vault references.
- Same Docker images run locally (compose) and in Azure — parity is the point.

---

## 8. Cross-Cutting Engineering Standards

- **Typed Python everywhere**; Pydantic v2 for all boundaries.
- **Async end-to-end** in the request path (FastAPI + SQLAlchemy async +
  httpx). CPU-bound work (embedding, PDF parsing) runs in a thread pool so it
  never blocks the event loop.
- **Structured logging** (JSON in production, pretty in dev) with request IDs.
- **Errors**: domain exceptions in services, translated to HTTP errors at the
  API layer only.
- **Tests**: pytest; services tested against fakes (e.g., in-memory vector
  store), API tested through FastAPI's test client.
- **Config**: 12-factor — everything from environment variables via
  `pydantic-settings`, one `.env.example` documenting every knob.
