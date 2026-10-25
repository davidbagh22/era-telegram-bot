Render deploy note: Dockerfile uses `alembic upgrade heads` so deploy does not fail when Alembic has more than one current head. A later cleanup PR should merge migration heads into one chain.
