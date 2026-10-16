# Margin in a container (Phase 6, D-066). Images pinned to exact versions approved by the owner
# (docs/DEPENDENCIES.md). The same image runs the web app and the worker.

# --- Build the web app -------------------------------------------------------------------------
FROM node:22.23.3-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
RUN npm run build

# --- Runtime -----------------------------------------------------------------------------------
FROM python:3.12.15-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MARGIN_ENV=production \
    MARGIN_DATA_DIR=/data \
    MARGIN_FRONTEND_DIST=/app/frontend/dist \
    MARGIN_HOST=0.0.0.0 \
    MARGIN_PORT=8000
WORKDIR /app/backend
# Exact versions with hashes, exported from backend/uv.lock: nothing unvetted is installed.
COPY backend/requirements.lock.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock.txt
COPY backend/ ./
COPY --from=frontend /src/frontend/dist /app/frontend/dist
RUN useradd --system --uid 10001 margin && mkdir -p /data && chown margin /data
USER margin
VOLUME ["/data"]
EXPOSE 8000
CMD ["sh", "-c", "python -m app.cli migrate && exec uvicorn --factory app.main:app_factory --host 0.0.0.0 --port 8000"]
