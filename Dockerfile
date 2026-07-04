# ---- stage 1: build the React frontend ----
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build            # -> /web/dist

# ---- stage 2: python backend serving API + built frontend ----
FROM python:3.12-slim AS app
# fonts so the (optional) corpus regeneration renders identically on Linux
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core fonts-liberation && rm -rf /var/lib/apt/lists/*
WORKDIR /srv/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
# the committed, deterministic corpus travels with the image
COPY --from=web /web/dist /srv/frontend/dist
EXPOSE 8000
ENV DEMO_PACE_MS=420
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
