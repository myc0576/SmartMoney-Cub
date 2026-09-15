# syntax=docker/dockerfile:1
#
# Container image for the hosted trader product.
#
# It installs the hosted extra, because hosted mode stores the journal in
# Postgres and the Postgres engine needs the psycopg driver. Without that extra
# the server still starts and then refuses to open the tenant store with a
# StoreError naming the exact install command, so the driver belongs in the
# image rather than in the operator's troubleshooting queue.
#
# The image bakes in no secret. The database URL, the access token, and the
# alphatech identity settings arrive as environment variables at run time.
#
# Build from the repository root so the build context contains the package:
#
#     docker build -f deploy/Dockerfile .
#
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    TRADER_PORT=8787

# A virtual environment keeps the installed package separate from the base
# interpreter, so a future base-image Python change cannot silently change what
# the console script resolves to.
RUN python -m venv /opt/venv

# A dedicated unprivileged account. The container runs as this user, so a
# process escape does not arrive as root.
RUN groupadd --gid 10001 smcub \
 && useradd --uid 10001 --gid 10001 --no-create-home \
      --home-dir /var/lib/smcub --shell /usr/sbin/nologin smcub

# /var/lib/smcub is the working directory. In hosted mode the journal lives in
# Postgres; this path holds the review workbench's own local state (assistant
# sessions and settings), so it is the one directory the container needs to
# write and the one directory worth a named volume.
RUN install -d -o smcub -g smcub -m 0750 /var/lib/smcub

WORKDIR /app

# pyproject.toml declares readme = "README.md", so the README is required for
# the build even though it is not used at run time.
COPY pyproject.toml README.md LICENSE ./
COPY src ./src

# The core install has no runtime dependency; the hosted extra adds
# psycopg[binary]>=3.2, which is what the Postgres tenant store needs.
RUN pip install ".[hosted]"

WORKDIR /var/lib/smcub

USER smcub

# The review workbench and the trader API share one socket, so one port serves
# both products.
EXPOSE 8787

# Liveness: the workbench shell answers 200 once the process is serving. When an
# access token is configured every surface requires it, including this one.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; req=urllib.request.Request('http://127.0.0.1:'+os.environ.get('TRADER_PORT','8787')+'/', headers={'X-SMCUB-Token': os.environ.get('TRADER_ACCESS_TOKEN','')}); urllib.request.urlopen(req, timeout=4)"

# Hosted mode needs the postgres URL, and a non-loopback bind needs the access
# token. Both are passed at run time; neither is baked into the image.
CMD ["/bin/sh", "-c", "exec smcub trader serve --mode hosted --host 0.0.0.0 --port \"$TRADER_PORT\" --database-url \"$DATABASE_URL\" --token \"$TRADER_ACCESS_TOKEN\" --no-browser"]
