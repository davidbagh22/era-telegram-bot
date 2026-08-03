FROM node:20-alpine AS miniapp-build

WORKDIR /miniapp

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=miniapp-build /miniapp/dist ./frontend/dist

CMD ["sh", "-c", "alembic upgrade heads && uvicorn app.webapp:app --host 0.0.0.0 --port ${PORT:-8000}"]
