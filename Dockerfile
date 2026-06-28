# ---------------------------------------------------------------------------
# Acopio — single-image build.
# Stage 1 builds the React SPA; stage 2 runs FastAPI and serves the built SPA.
# Works on Render (runtime: docker), Fly.io, or any container host.
# ---------------------------------------------------------------------------

# --- Stage 1: build frontend ---
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- Stage 2: backend runtime ---
FROM python:3.13-slim
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY --from=frontend /app/frontend/dist ./frontend/dist

# Writable data dir for the SQLite fallback + librarian vector cache.
RUN mkdir -p /app/data
EXPOSE 8000

# Shell form so ${PORT} (injected by Render/Fly) is expanded.
CMD uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000}
