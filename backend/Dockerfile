#
# Backend image — FastAPI/uvicorn + Celery worker + Celery beat (one image,
# different commands set per service in docker-compose.yml). v0.7.2 hardened.
#
# Non-root: runs as `appuser` with UID matching the host so the bind-mounted
# ./backend:/app volume is writable for __pycache__ and celerybeat-schedule.db.
# Override at build via --build-arg APP_UID=<your_id> if your host UID isn't
# 1002. Compose's build.args (or top-level x-uid extension) is the cleanest
# way to keep this in sync.

FROM python:3.12-slim

ARG APP_UID=1002
ARG APP_GID=1002

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Runtime deps: curl for the HTTP healthcheck. psycopg[binary] ships its
# own libpq, so libpq-dev is not needed at build time. bcrypt has wheels
# for cpython 3.12 — no build deps either.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps as root before dropping privilege so site-packages
# stays root-owned and read-only for appuser.
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user matching the host UID. Bind-mount of ./backend:/app
# means container writes to /app land on the host filesystem; UID match
# avoids permission errors on __pycache__, .pytest_cache, celerybeat schedule.
RUN groupadd --gid ${APP_GID} appuser \
    && useradd --uid ${APP_UID} --gid ${APP_GID} --create-home --shell /usr/sbin/nologin appuser

# Source is bind-mounted at runtime via compose; the COPY here is for
# image-only deployments (no bind-mount, e.g. production). --chown ensures
# appuser owns it in that case. Bind-mount overlays this at runtime.
COPY --chown=${APP_UID}:${APP_GID} . /app

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

EXPOSE 8000

# Default command is the API. Compose overrides per service (worker, beat).
# The entrypoint shim is set in compose, not here, so worker/beat inherit it
# the same way and the image stays generic.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
