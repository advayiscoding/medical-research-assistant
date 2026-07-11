# Deployment Guide — Azure

This document covers deploying MedResearch AI to Azure. The same Docker images
that run locally via `docker compose` run in the cloud — parity is the point, so
"works on my machine" and "works in prod" are the same artifact.

## 1. Target Architecture — Azure Container Apps

We use **Azure Container Apps (ACA)** rather than AKS: it gives serverless
containers with scale-to-zero and no Kubernetes cluster to operate — the right
size for this workload while still being genuinely production-shaped.

```
                          ┌──────────────────────────────────────┐
   Internet ────HTTPS────▶│  Container Apps Environment           │
                          │                                       │
                          │  ┌───────────┐      ┌──────────────┐  │
                          │  │ frontend  │─────▶│   backend    │  │
                          │  │ (Next.js) │      │  (FastAPI)   │  │
                          │  │ ext ingress│     │ ext ingress  │  │
                          │  └───────────┘      └──────┬───────┘  │
                          │                     ┌──────▼───────┐  │
                          │                     │   chromadb   │  │
                          │                     │ int ingress  │  │
                          │                     │ + Azure Files│  │
                          │                     └──────────────┘  │
                          └───────────────┬──────────────────────┘
                                          │
              ┌───────────────────────────┼───────────────────────────┐
              ▼                           ▼                           ▼
   Azure Database for            Azure Key Vault            Azure Container
   PostgreSQL Flexible Server    (JWT secret,               Registry (ACR)
   (managed, backups, TLS)       Claude API key, DB pwd)    (image storage)
```

**Component mapping**

| Local (compose) | Azure |
|---|---|
| `postgres` container | Azure Database for PostgreSQL Flexible Server (managed) |
| `chromadb` container | ACA container app with an Azure Files volume (internal ingress only) |
| `backend` container | ACA container app, external ingress, min-replicas 1 |
| `frontend` container | ACA container app, external ingress |
| `.env` file | Key Vault secrets + ACA env vars |
| local image build | images pushed to ACR |

**Why these choices**

- **Postgres is managed, not a container.** The database is the system of
  record; it needs backups, point-in-time restore, patching, and TLS — all of
  which the managed service provides and a container in a stateless platform
  does not.
- **ChromaDB uses internal ingress + a persistent Azure Files volume.** It's a
  derived index (rebuildable from Postgres), but persisting it avoids re-embedding
  the whole corpus on every restart. Internal ingress means only the backend can
  reach it — it's never exposed to the internet.
- **Backend min-replicas = 1.** The embedding model loads on startup (a few
  seconds); scale-to-zero would put that cost on the first user after every idle
  period. One warm replica avoids that. The frontend can scale to zero safely.

## 2. Secrets & Configuration

**Never** bake secrets into images or commit them. Three tiers:

| Secret | Local | Azure |
|---|---|---|
| `JWT_SECRET` | `.env` | Key Vault → ACA secret ref |
| `ANTHROPIC_API_KEY` | `.env` | Key Vault → ACA secret ref |
| Postgres password | `.env` | Key Vault; injected into `DATABASE_URL` |
| `PUBMED_API_KEY` | `.env` | Key Vault (optional) |

In ACA, secrets are referenced as `secretref:` in the container app's env, and
the values are pulled from Key Vault via the app's **managed identity** — so no
credential ever appears in a template, image, or log.

Production config differences (all via env, no code change — see
`app/core/config.py`):

- `ENVIRONMENT=prod` → JSON structured logging; startup **refuses to boot** if
  `JWT_SECRET` is still the dev default (guard in `app/main.py`).
- `CORS_ORIGINS` set to the real frontend URL, not `localhost:3000`.
- `NEXT_PUBLIC_API_URL` (frontend build arg) set to the backend's public URL.

## 3. Provisioning (az CLI outline)

```bash
# 0. Prereqs: az login; pick a region; set names
RG=medresearch-rg; LOC=eastus; ACR=medresearchacr

az group create -n $RG -l $LOC

# 1. Container registry + push images
az acr create -n $ACR -g $RG --sku Basic --admin-enabled true
az acr build -r $ACR -t backend:latest ./backend
az acr build -r $ACR -t frontend:latest \
  --build-arg NEXT_PUBLIC_API_URL=https://<backend-fqdn>/api ./frontend

# 2. Managed Postgres
az postgres flexible-server create -g $RG -n medresearch-pg \
  --tier Burstable --sku-name Standard_B1ms \
  --admin-user medresearch --admin-password "<from-keyvault>" \
  --database-name medresearch --version 16

# 3. Key Vault + secrets
az keyvault create -g $RG -n medresearch-kv
az keyvault secret set --vault-name medresearch-kv -n jwt-secret --value "<rand>"
az keyvault secret set --vault-name medresearch-kv -n anthropic-key --value "<key>"

# 4. Container Apps environment + apps
az containerapp env create -g $RG -n medresearch-env -l $LOC
# chromadb (internal), backend (external), frontend (external) —
# each: az containerapp create ... with --secrets and env refs.
```

The `az containerapp create` calls wire env vars exactly as `docker-compose.yml`
does (`DATABASE_URL`, `CHROMA_HOST`, `JWT_SECRET`, `ANTHROPIC_API_KEY`, …), with
secrets sourced from Key Vault. Because the images and env contract are identical
to local, there is no prod-only code path to debug.

## 4. Database Migrations in Production

The backend image applies `alembic upgrade head` on startup
(`docker-entrypoint.sh`), and migrations are idempotent, so a rolling deploy is
safe: a new revision boots, migrates (no-op if already current), then serves.
For a breaking migration, use the standard expand/contract pattern (add nullable
column → backfill → deploy code → drop old column) so old and new revisions
coexist during the rollout.

## 5. Post-Deploy Verification

```bash
curl https://<backend-fqdn>/api/health          # {"status":"ok"}
# then exercise register → search → chat through the frontend URL
```

## 6. Cost & Scaling Notes

- **Burstable Postgres (B1ms)** and **scale-to-zero frontend** keep idle cost
  minimal; the one always-on backend replica is the main fixed cost.
- Scale the backend on HTTP concurrency; embedding is CPU-bound, so scale on CPU
  too if search/ingest volume grows.
- The single biggest future optimization is moving paper ingestion to a
  background worker (Azure Container Apps **jobs** or a queue) so user-facing
  search latency is decoupled from embedding throughput.

## Future Hardening (documented, not implemented)

- Refresh-token rotation and password reset (current auth is access-token only).
- Rate limiting at the ingress (APIM or ACA rules).
- Private endpoints for Postgres/Key Vault (VNet integration) instead of public
  access with firewall rules.
