# CROVIA backend.
#
# The geography file lives under crovia-ui/, not under backend/, because the
# Expo bundler can only read JSON from inside its own project while Python can
# read any path. That means the build context has to be the repository root
# rather than backend/, which is why the paths below are repo-relative:
#
#     docker build -f backend/Dockerfile -t crovia .
#
FROM python:3.12-slim

# psycopg2 needs libpq at runtime. The -binary wheel bundles the rest.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first, so editing code does not reinstall them on every build.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
# Only the geography, not the whole app. It is the one file the backend reads
# from the other side of the repository.
COPY crovia-ui/src/geo/ ./crovia-ui/src/geo/

WORKDIR /app/backend
ENV PYTHONPATH=/app/backend

# Run as a normal user. A container that does not need root should not have it.
RUN useradd --create-home --uid 10001 crovia && chown -R crovia /app
USER crovia

# The host tells us which port to listen on, and it is not always 8000.
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
