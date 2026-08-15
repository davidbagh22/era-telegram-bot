FROM node:20-alpine AS miniapp-build

WORKDIR /miniapp

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Keep pg_dump compatible with Render's PostgreSQL 18 default. The Debian
# `postgresql-client` metapackage can lag the database major and pg_dump then
# refuses the snapshot before checksum/restore verification can run.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl fonts-dejavu-core; \
    install -d /usr/share/postgresql-common/pgdg; \
    curl --fail --silent --show-error \
      -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
      https://www.postgresql.org/media/keys/ACCC4CF8.asc; \
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends postgresql-client-18; \
    pg_dump --version | grep -Eq 'PostgreSQL\) 18\.'; \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=miniapp-build /miniapp/dist ./frontend/dist

CMD ["sh", "-c", "alembic upgrade heads && uvicorn app.webapp:app --host 0.0.0.0 --port ${PORT:-8000}"]
