# 📦 Acopio — Smart inventory for relief operations

**Acopio** (Spanish for a *supply-collection center*) is an open-source, AI-native
inventory system built for humanitarian relief logistics — originally for a
volunteer operation routing donated supplies **through Curaçao to Venezuela**
after the recent earthquakes.

It replaces the manual Excel workflow with something that is fast, accountable,
and genuinely easy to use: drop in any spreadsheet and it gets normalized,
categorized and de-duplicated automatically; dictate "we just received 200 boxes
of rice from the Red Cross" and it records the intake under your name; ask "which
medical supplies are running low?" and get a real answer.

> Built to be copied. This is a public repository — fork it for your own relief
> operation.

---

## What it does

- **Import any Excel/CSV** — whatever the columns look like. Powered by the
  [`librarian`](https://github.com/juanlavieri/librarian) intake pipeline
  (`parse → profile → embed`), Acopio maps messy human columns onto a clean
  canonical model.
- **Smart normalization** — classifies every item (food / water / medical /
  hygiene / shelter / clothing / tools / baby) and **merges duplicates**
  ("Arroz 1kg" ≈ "Rice 1 kg bag") using semantic embeddings.
- **Agentic assistant with voice** — a tool-calling AI that can search, run
  read-only SQL analytics ("code execution"), take stock **in/out**, and even
  **evolve the schema** (add a field or a whole new table) on request. Press the
  mic and just talk (OpenAI Whisper, with a browser-speech fallback).
- **Accountability** — every movement is tied to the volunteer **and the
  collection center**; an immutable **audit log** records every action.
- **Live dashboards** — what's coming in, what's going out, by category, by
  volunteer, low-stock alerts. Scoped to the centers you oversee.
- **Org hierarchy** — Country Manager → Regional Manager → Center Manager →
  Volunteer. Each level creates and manages the people, centers and inventory
  below it; inventory is tracked per collection center and visible up the chain.
- **Bilingual (Español / English)** — every screen, menu and message, with a
  one-tap language switch (defaults to the browser language).
- **Mobile-first & responsive + installable PWA** — collapses to a hamburger
  menu and bottom-sheet dialogs on phones, installs to the home screen, and the
  app shell works offline (vital where field connectivity is poor).
- **Expiry, batches & FEFO** — intake records lot + expiry; dispatch depletes
  **First-Expired-First-Out**. Items are flagged expired / <30d / <90d / <180d
  per Logistics Cluster guidance, with one-click **disposal** of expired stock.
- **Alerts** — a dedicated screen (and dashboard KPIs) for expired, expiring and
  **low-stock vs per-item reorder thresholds**, so nothing is quietly lost.
- **Requests / requisitions** — log what the field needs with priority and SLA
  date; **fulfilling a request records a real FEFO dispatch**, matching supply
  to demand with full traceability.
- **Movement reasons** — donation / purchase / transfer, and
  distributed / transferred / **damaged / expired / lost** — so losses are
  visible, not invisible.
- **CSV exports** — inventory, movements and expiring stock, for donor and
  coordination reporting.
- **Runs with zero AI key too** — falls back to offline heuristics + librarian's
  hashing embedder, so it always works; add a key to make it brilliant.

## Architecture

| Layer | Choice | Why |
|-------|--------|-----|
| Backend | **FastAPI** (Python) | imports `librarian` directly for intake/normalization/semantic search |
| Data normalization | **librarian** (`librarian-ai`) | reuses the `IntakeItem → Reader → profile_document → embeddings` substrate |
| Database | **Postgres** (prod) / **SQLite** (local) | graceful fallback, no setup needed locally |
| AI | **OpenAI** (chat + embeddings + Whisper) | normalization, agent, dedup, voice — all optional |
| Frontend | **React + Vite + Tailwind + Recharts** | modern UI, built to static and served by FastAPI (single service) |
| Deploy | **Docker → Render / Fly.io** | free `*.onrender.com` / `*.fly.dev` URL, no domain to buy |

It deploys as **one service** (FastAPI serves both the API and the built SPA),
following the same single-service pattern as our crypto-pay deployment.

---

## Run locally

Requires Python 3.11–3.13 and Node 18+.

```bash
# 1. Backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Frontend (build once; served by the backend)
cd frontend && npm install && npm run build && cd ..

# 3. (optional) configure
cp .env.example .env        # add OPENAI_API_KEY to enable AI features

# 4. Run
uvicorn app.main:app --app-dir backend --reload --port 8000
# open http://localhost:8000  → register the first account (becomes the country manager)
```

**Hot-reloading frontend dev** (optional): in a second terminal run
`cd frontend && npm run dev` and open http://localhost:5173 — it proxies `/api`
to the backend on :8000.

Try importing `examples/sample_inventory.csv` to see normalization,
classification and dedup in action.

### Smoke test

```bash
source .venv/bin/activate && python backend/smoke_test.py
```

---

## Deploy (no domain required)

### Render (recommended)

1. Push this repo to GitHub.
2. Render → **New → Blueprint** → select the repo (`render.yaml` is detected).
   It provisions a free Postgres + the web service.
3. In the service's **Environment** tab, paste `OPENAI_API_KEY` (optional but
   recommended).
4. Deploy → you get `https://acopio.onrender.com`.

### Fly.io

```bash
fly launch --no-deploy
fly postgres create && fly postgres attach <pg-app>
fly secrets set SECRET_KEY=$(openssl rand -hex 32) OPENAI_API_KEY=sk-...
fly deploy        # → https://acopio.fly.dev
```

---

## Configuration

All via environment variables (see `.env.example`):

| Var | Default | Purpose |
|-----|---------|---------|
| `DATABASE_URL` | *(SQLite)* | Postgres URL in production |
| `SECRET_KEY` | dev value | signs session tokens — **set in prod** |
| `ADMIN_EMAIL` | `admin@acopio.org` | first account with this email is admin |
| `OPENAI_API_KEY` | *(unset)* | enables AI assistant, smart normalization, voice |
| `OPENAI_MODEL` | `gpt-4o-mini` | chat/normalization model |
| `OPENAI_EMBED_MODEL` | `text-embedding-3-small` | dedup/semantic search |
| `OPENAI_TRANSCRIBE_MODEL` | `whisper-1` | voice transcription |

---

## Security notes

- Passwords hashed with PBKDF2-HMAC-SHA256; sessions are random bearer tokens
  with a 7-day TTL.
- Access is **scoped by role and center**: a user only sees and acts on the
  collection centers within their slice of the hierarchy. After the first
  (country-manager) account, registration is closed — managers create accounts.
- The assistant's SQL "code execution" tool is **read-only** (SELECT only,
  single statement, row-capped) and is **blocked from the `users`/`sessions`
  tables**. All mutations go through validated, audited action tools.
- Set a strong `SECRET_KEY` and keep `OPENAI_API_KEY` out of git (it is, by
  default).

## License

Apache-2.0. Use it, fork it, help people with it.
