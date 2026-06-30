FROM node:22-alpine AS frontend-build

WORKDIR /frontend
COPY frontend/package.json frontend/pnpm-workspace.yaml ./
RUN corepack enable && pnpm install --no-frozen-lockfile
COPY frontend/ .
RUN pnpm build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=frontend-build /frontend/dist /app/frontend/dist

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.webapp:app --host 0.0.0.0 --port ${PORT:-8000}"]
