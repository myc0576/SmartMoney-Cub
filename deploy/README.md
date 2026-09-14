# Deploying the hosted trader product

The product is one process: the trader API and the review workbench share a
single socket and a single port. Hosted mode authenticates every request
against the alphatech platform and keeps each tenant's journal in Postgres.
Nothing here places, cancels, or modifies anything at a broker; the execution
ban is part of the shipped contract and the server prints
`READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE` on start.

This directory holds three routes, from the quickest to the most durable:

| Route | Use it when | Files |
| --- | --- | --- |
| [Compose](#route-1-docker-compose) | You want the app and its database together, on a laptop or a single host. | `deploy/docker-compose.yml`, `deploy/Dockerfile` |
| [Image only](#route-2-the-image-against-a-managed-postgres) | The database is managed for you and you just need the app. | `deploy/Dockerfile` |
| [systemd + nginx](#route-3-systemd-and-nginx-on-a-plain-host) | No container runtime on the host, and you want TLS terminated by nginx. | `deploy/trader.service`, `deploy/nginx.conf` |

## What the server does, before anything else

One command serves both products:

    smcub trader serve [--host H] [--port P] [--mode {local,hosted}] \
        [--database-url URL] [--state-dir DIR] [--token TOKEN] [--no-browser]

Three refusals are deliberate, and a deployment that trips one of them is
misconfigured rather than unlucky:

- `--mode hosted` **requires** `--database-url` with a `postgresql://` URL. There
  is no fallback to SQLite. A hosted tenant whose journal landed in a local
  file would look like it worked, and that is the failure this refusal exists
  to prevent.
- A non-loopback bind (`--host 0.0.0.0`) **requires** `--token`. Without it the
  server exits 2.
- `--database-url` in local mode is refused. If you passed a Postgres URL you
  meant hosted, and quietly writing a local file would put the data somewhere
  other than where you expect it.

`smcub workbench` is a different command and does **not** mount `/api/trader/*`.
Only `smcub trader serve` serves both products.

On start the server writes to stderr:

    smartmoney-cub trader: http://127.0.0.1:8787/
    mode: hosted
    store: postgresql://(configured)
    READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE

Only the URL scheme is printed for a hosted store, because a database URL can
carry a password.

### Identity

Hosted mode resolves a platform identity on every request and never
authenticates anonymously. Two environment variables choose how:

| Variable | Default | Meaning |
| --- | --- | --- |
| `ALPHATECH_AUTH_MODE` | `session` | `session` forwards the caller's platform session cookie to the platform; `hmac` verifies a signed identity header. |
| `ALPHATECH_BASE_URL` | `https://alphatech.net.cn` | The platform site root, not the `/v1` model-gateway base. |
| `ALPHATECH_SSO_SECRET` | unset | Required in `hmac` mode. Absent means fail-closed: every request is refused with `401`. |

In `session` mode the cookie is forwarded to
`{ALPHATECH_BASE_URL}/api/user/self`; a `200` carrying an `id` is the identity,
and a successful lookup is cached for 60 seconds. A platform id maps to a
stable tenant `alphatech:<id>`. Any other value of `ALPHATECH_AUTH_MODE`
fails closed.

### Health

`GET /api/trader/health` answers `{"status":"ok", ... "safety":"READ_ONLY_NO_ORDER_NO_CANCEL_NO_TRADE"}`
and needs a verifiable identity, exactly like every other route. The
container and compose healthchecks therefore probe `/` (the interface shell)
and send the access token when one is configured. The workbench's own
`/api/doctor` is **not** part of the trader surface: it is unauthenticated
local tooling, and it should not be published.

## Route 1: Docker Compose

This brings up Postgres 16 and the app together, with a healthcheck on each and
two named volumes. The database is not published to the host; only the app's
port is bound, and only to loopback by default.

    cd /path/to/smartmoney-cub-harness

    export POSTGRES_PASSWORD="$(openssl rand -hex 24)"
    export TRADER_ACCESS_TOKEN="$(openssl rand -hex 32)"
    # Only needed for ALPHATECH_AUTH_MODE=hmac:
    # export ALPHATECH_SSO_SECRET="$(openssl rand -hex 32)"

    docker compose -f deploy/docker-compose.yml up --build -d

    # The app waits for Postgres to report healthy, so this is a real check
    # rather than a race against initialization.
    curl -sf -H "X-SMCUB-Token: $TRADER_ACCESS_TOKEN" \
        "http://127.0.0.1:8787/api/trader/health" | head -c 400

    docker compose -f deploy/docker-compose.yml ps

Both services should read `healthy`. To stop it without losing data:

    docker compose -f deploy/docker-compose.yml down

`down` keeps the `db_data` and `smcub_state` volumes, so the journal survives.
`docker compose ... down -v` deletes them, and with them the journal; do not
run that against a store you care about.

Variant: use the existing command-line server instead of the container. It is
the same product, and it is useful when the database is local and the app does
not need containerizing:

    python -m pip install -e ".[hosted]"
    python -m smartmoney_cub_harness.cli trader serve \
        --mode hosted --host 0.0.0.0 --port 8787 \
        --database-url "postgresql://smcub:$POSTGRES_PASSWORD@127.0.0.1:5432/smcub" \
        --token "$TRADER_ACCESS_TOKEN" --no-browser

## Route 2: the image against a managed Postgres

Buildable from the repository root; the Dockerfile installs `.[hosted]`, which
is what pulls `psycopg[binary]>=3.2`. Without it the server starts and then
fails to open the tenant store with a `StoreError` naming the install command,
so the driver is in the image rather than in your troubleshooting queue.

    cd /path/to/smartmoney-cub-harness
    docker build -f deploy/Dockerfile -t smartmoney-cub-trader:1.0.0 .

    export DATABASE_URL="postgresql://USER:PASSWORD@db.example.com:5432/smcub?sslmode=require"
    export TRADER_ACCESS_TOKEN="$(openssl rand -hex 32)"
    export ALPHATECH_AUTH_MODE=session
    # export ALPHATECH_SSO_SECRET="..."   # required when the mode is hmac

    docker run --rm -d --name smcub-trader \
        -e DATABASE_URL -e TRADER_ACCESS_TOKEN \
        -e ALPHATECH_AUTH_MODE -e ALPHATECH_BASE_URL \
        -v smcub_state:/var/lib/smcub \
        -p 127.0.0.1:8787:8787 \
        smartmoney-cub-trader:1.0.0

The image runs as the unprivileged user `smcub` (uid 10001). It bakes in no
secret; the database URL and the token are required environment variables, and
the server refuses to start without either. Point the database's schema at a
database this product owns: it manages its own tables and is not a general
multi-tenant database host.

Before this faces the internet, put `deploy/nginx.conf` in front of it for TLS
and the `/trader` prefix, and keep `-p 127.0.0.1:8787:8787` rather than
publishing the port directly.

## Route 3: systemd and nginx on a plain host

### 1. Install the package and the service account

    sudo useradd --system --create-home --home-dir /var/lib/smcub \
        --shell /usr/sbin/nologin smcub
    sudo python3 -m venv /opt/smcub/venv
    sudo /opt/smcub/venv/bin/pip install ".[hosted]"

The service account is used only by this unit. It owns no login shell and the
server never runs as root.

### 2. Put the secrets where only root and the service can read them

    sudo install -d -m 0750 -o root -g smcub /etc/smcub
    sudo sh -c 'umask 0027; cat > /etc/smcub/trader.env' <<'ENV'
    DATABASE_URL=postgresql://smcub:CHANGEME@127.0.0.1:5432/smcub
    TRADER_ACCESS_TOKEN=CHANGEME
    ALPHATECH_AUTH_MODE=session
    ALPHATECH_BASE_URL=https://alphatech.net.cn
    ALPHATECH_SSO_SECRET=
    ENV
    sudo chown root:smcub /etc/smcub/trader.env
    sudo chmod 0640 /etc/smcub/trader.env

Replace both `CHANGEME` values, URL-encode the database password, and fill in
`ALPHATECH_SSO_SECRET` only if you switched the mode to `hmac`. In `session`
mode an empty secret is harmless, and in `hmac` mode it is fail-closed rather
than fail-open.

### 3. Start the service

    sudo install -m 0644 deploy/trader.service /etc/systemd/system/smcub-trader.service
    sudo systemctl daemon-reload
    sudo systemctl enable --now smcub-trader
    systemctl status smcub-trader --no-pager
    sudo journalctl -u smcub-trader -n 40 --no-pager

The unit runs `--mode hosted --host 127.0.0.1 --port 8787` with
`--database-url` and `--token` read from `/etc/smcub/trader.env`,
`Restart=on-failure`, and a modest sandbox (`ProtectSystem=strict`,
`ProtectHome=yes`, `NoNewPrivileges=yes`). It binds loopback on purpose:
nginx is what faces the network.

### 4. Terminate TLS and publish the prefix with nginx

    sudo cp deploy/nginx.conf /etc/nginx/conf.d/smcub-trader.conf
    # Keep only the 'map' and the two 'server' blocks; drop this file's
    # 'events' and 'http' wrappers on a distribution nginx.
    sudo nginx -t && sudo systemctl reload nginx

Replace the four TLS placeholders and the `server_name` first — they are listed
at the top of `deploy/nginx.conf`. The product is published as a peer entry on
the alphatech platform, at `https://alphatech.net.cn/trader`, and the
`location /trader/` block strips the prefix before the app sees the request.
The trailing slash on both the location and `proxy_pass` is what makes that
rewrite work, and `proxy_buffering off` is what keeps the review assistant's
streamed turns live instead of frozen until the turn ends.

Then verify from outside:

    curl -sf -H "X-SMCUB-Token: $TRADER_ACCESS_TOKEN" \
        https://trader.example.com/trader/api/trader/health | head -c 400

### 5. Publish it as a platform entry

The product joins the alphatech platform as a peer of Alpha Canvas and the
Commerce Workbench, at `alphatech.net.cn/trader`. Requests arrive carrying the
caller's platform session cookie, and the product resolves that cookie to a
tenant; it implements no registration and stores no password of its own. Point
the platform's entry at the `/trader` path you have just stood up, and keep
`ALPHATECH_AUTH_MODE` and `ALPHATECH_BASE_URL` consistent with the platform the
users actually sign in to.

## Operating notes

### Prove the deployment before you trust it

`scripts/hosted-e2e.py` runs the exact configuration this document describes —
Postgres plus platform identity plus two tenants — against a real database, and
asserts the properties a hosted deployment must have: each tenant sees only their
own journal, an unauthenticated request is refused with 401, a request with a
tampered signature is refused, every refusal still carries the safety declaration,
and the rows land under separate tenant ids in Postgres.

It checks **both** identity modes. Session mode runs first, because it is the
default this document sets and the only mode a browser can reach: the frontend
sends no auth header and relies on the platform cookie the browser already holds,
so the check stands up a local stub that answers `/api/user/self` the way the
platform does. Signed-header mode is the fallback and is checked second. A
deployment can pass every signed-header test and still refuse every real user, so
both are asserted rather than one assumed.

```bash
pip install "smartmoney-cub-harness[hosted]" pgserver
SMARTMONEY_HOSTED_E2E=1 python scripts/hosted-e2e.py
```

`pgserver` gives the check a throwaway PostgreSQL it starts and discards, so this
runs on a workstation with no database installed. Point it at your own server
instead by removing `pgserver` and starting the product yourself; the assertions
are the part worth repeating against your real deployment.

Without `SMARTMONEY_HOSTED_E2E=1` the script prints why it skipped and exits 0,
so it never turns into a false failure on a machine that cannot host a database.

### Check the proxy config and the container healthcheck

### Pre-flight the deployment before users see it

```bash
python scripts/preflight.py                  # local mode
python scripts/preflight.py --mode hosted --database-url "$DATABASE_URL"
```

This is the check worth running before you point anyone at the product, and again
after any configuration change. It executes the deployment's own shape rather than
describing it: starts the product the way the service units start it (loopback bind,
required access token), puts the shipped proxy rules in front of it, and asserts
what a launch depends on —

- every spelling of an API path needs the token (`/api`, `/api/`, `/api/trader/health`,
  `/api/overview`, `/api/settings`, `/api/audit`)
- the interface and client-side routes load without one, because a browser cannot
  send that header on a page load
- the proxy's token injection reaches the app, so a browser can actually use the
  product
- a misconfigured `ALPHATECH_AUTH_MODE` is refused rather than falling open
- the safety contract holds: declaration present, execution disabled, no broker API

It exits non-zero with the failing checks named. **Every late defect in this build
lived in this path** — the nginx prefix, the token gate, the bare `/api` spelling,
the multi-user advisory, the release workflow — because configuration and
documentation were reviewed but never executed. This script executes them.

The proxy it puts in front is a stand-in that applies the config's own routing
rules, not nginx itself. On a host with nginx installed, run the real thing; this
exists so the path can be exercised on a machine that has none.

Two more pieces of this deployment are executable and worth running before you
trust them:

```bash
pip install crossplane
python scripts/nginx-check.py       # parses nginx.conf; catches the syntax and
                                    # unknown-variable faults that stop nginx starting
```

An nginx config that fails to parse, or that references a variable no `map`
defines, takes the whole site down and never appears in a test suite. This check
parses the shipped config, confirms every variable is either built in or mapped,
and confirms the pieces a hosted deployment depends on are present. crossplane is
a parser rather than nginx, so on a host with nginx installed run
`nginx -t -c` for the authoritative answer — the check says so when it passes.

The container's `HEALTHCHECK` is likewise a claim about the image. It is a plain
Python URL request, so it can be run directly against a server started the way the
container starts one, including the access token the container passes — the part
most likely to be wrong. A correct token must report healthy, and a wrong token or
a stopped app must report unhealthy; a healthcheck that passes in both states is
worse than none, because it hides the failure it exists to catch.

- **Back up the journal.** In hosted mode it is the `db_data` volume (compose)
  or your Postgres instance. It is the user's own data and it is never in the
  repository.
- **The token is required, not optional.** A non-loopback bind refuses to start
  without it, and the interface and the trader surface share one gate. Clients
  send `X-SMCUB-Token`.

  **nginx supplies it for browsers.** A browser cannot attach a custom header to
  the navigation that loads a page, or to the requests the page then makes for its
  own JavaScript and CSS — so a token-protected app is unreachable from a browser
  unless the proxy adds the header. `deploy/nginx.conf` does that: it includes a
  one-line snippet holding the token and sets `X-SMCUB-Token` on every proxied
  request. Create it once, with the same value as the service's
  `TRADER_ACCESS_TOKEN`:

  ```bash
  sudo install -d -m 0755 /etc/nginx/snippets
  printf 'set $smcub_token "%s";\n' "$(openssl rand -hex 32)" \
    | sudo tee /etc/nginx/snippets/smcub-token.conf >/dev/null
  sudo chmod 600 /etc/nginx/snippets/smcub-token.conf
  ```

  A missing snippet makes nginx refuse to start, which is the failure you want: a
  proxy that came up without the token would 401 every request. The include keeps
  the secret out of this repository and out of the config file's history.

  The page and its assets are served without the token, and every API call still
  requires it. That split is deliberate: the shell is identical bytes for everyone
  and shows nothing on its own, because every number it displays arrives through a
  gated call.
- **The local workbench API is not the product, and the shipped config closes
  it.** `/api/overview`, `/api/settings`, and `/api/assistant/*` read the
  container's own state directory and carry no tenant identity, so every visitor
  the proxy serves would see the same data -- including other users' assistant
  sessions. `deploy/nginx.conf` therefore publishes only
  `/trader/api/trader/*` and returns `403` for the rest of `/trader/api/`, and
  `scripts/preflight.py` asserts that boundary rather than trusting it.
  Commenting those two blocks out is correct only on a host that serves one
  person and is reachable by no one else; the blocks carry a comment saying so.
  The access token does **not** close this on its own: nginx injects it for
  every visitor, because a browser cannot send a custom header on a page load,
  so it cannot tell one person from another.
- **Never commit a real deployment's `.env`.** The compose file takes every
  secret from the environment for exactly this reason.
- **Hosted extra is opt-in.** The core install has no runtime dependency and
  stays that way; `psycopg` arrives only with `[hosted]`.

The product's scope, its non-goals, and the features deferred past v1 are
documented in `docs/trader-product.md`.
