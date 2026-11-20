# Stage 1: Build OMRKit Web Studio (React + Vite + Tailwind)
FROM node:22-slim AS studio-builder
WORKDIR /app/studio
COPY studio/package.json studio/package-lock.json ./
RUN npm ci
COPY studio/ ./
RUN npm run build

# Stage 2: Minimal Python runtime serving REST API + Web Studio
FROM python:3.11-slim AS runtime
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/
COPY --from=studio-builder /app/src/omrkit/api/static ./src/omrkit/api/static

RUN pip install --upgrade pip && pip install ".[all]"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"

CMD ["omrkit", "studio", "--host", "0.0.0.0", "--port", "8000"]
