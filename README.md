# lametric-exoscale-status

A small Flask API that displays the status of [Exoscale](https://www.exoscale.com)
on a [LaMetric Time](https://www.lametric.com/) clock. It reads the status of
Exoscale services from the [StatusPal](https://statuspal.eu) public API
(v2, open data — no authentication required) and serves it to the clock as
JSON frames.

For users who only want the clock app, install
[**Exoscale status**](https://apps.lametric.com/apps/exoscale_status/5807)
on your device — it just works.

## Architecture

```
app/
├── app.py                  # Flask application factory + routes
├── config.toml             # static configuration
├── gunicorn.conf.py        # hardened gunicorn settings
└── lib/
    ├── models.py           # domain models (Status, Service, Zone, Notice, StatusData)
    ├── configuration.py    # TOML config loading (typed, validated)
    ├── statuspal_parser.py # StatusPal v2 public summary payload -> domain models
    ├── statuspal_client.py # HTTP client with retry/backoff (public open-data API)
    ├── cache.py            # TtlCache + single-flight CachedFetch
    ├── subscription.py     # parsing of the ?zones= / ?services= parameters
    ├── security.py         # security headers + sliding-window rate limiter
    └── frames.py           # StatusData -> LAMETRIC frames
```

Data flow: `StatusPalClient.fetch_status_data()` fetches the public v2
summary (page status, services, zones, incidents and maintenances) in a
single request, parses it into `StatusData`, and caches the result for
30 s (single-flight). The clock polls `GET /api/v1/`, which turns the
snapshot into frames (icon + text).

## Public endpoints

| Endpoint            | Description                                          |
| ------------------- | ---------------------------------------------------- |
| `GET /`             | API description, version, subscription documentation |
| `GET /healthz`      | Liveness probe (`{"status": "ok"}`)                   |
| `GET /api/v1/`      | LAMETRIC frames for the clock                        |
| `GET /api/v1/status`| Aggregated status (current status, impacted count, incidents, maintenances) |
| `GET /api/v1/zones` | Per-zone (container) status and services             |
| `GET /api/v1/services` | Global services list                               |
| `GET /api/v1/incidents`    | Active incidents                                     |
| `GET /api/v1/maintenances` | Pending / in-progress maintenances                 |

When the upstream StatusPal API is unavailable, `/api/v1/` still answers
`200` with a `Status unavailable` frame so the clock keeps displaying
something, while the JSON endpoints answer
`503 {"error": "upstream_unavailable"}`.

## LAMETRIC subscription

`GET /api/v1/` accepts two optional query parameters to limit what is shown:

| Parameter  | Values                                                              |
| ---------- | ------------------------------------------------------------------- |
| `zones`    | comma-separated zone slugs, e.g. `CH-GVA-2,CH-DK-2`                 |
| `services` | comma-separated service slugs or names, e.g. `Compute,API`          |

Example: `https://host/api/v1/?zones=CH-GVA-2&services=Compute,API`

Values are case-insensitive; malformed values or more than 20 values per
parameter return `400`.

## Configuration

Static settings live in `app/config.toml`: StatusPal base URL and subdomain,
request timeout, cache TTL, rate limit, log level, LAMETRIC app name/logo
and the status icons.

The StatusPal API (v2) is public open data: **no API key is used**. The
client sends no credentials at all — not even when the environment could
provide one — and the configuration model has no key field to fill.

## Security

- Sliding-window rate limit per client IP (default 120 req/min, `429` when exceeded)
- 30 s response cache, single-flight upstream fetch (no request storms)
- Security headers on every response (`nosniff`, `DENY`, `no-referrer`, `no-store`)
- Public API only: no credentials anywhere (environment, config, repository)
- Hardened gunicorn (request line/field size and count limits, worker recycling)
- Docker image runs as a non-root user
- JSON-only error handlers (no traceback leakage)

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt

.venv/bin/pytest -q
.venv/bin/ruff check app tests
.venv/bin/mypy app tests
```

The codebase is strongly typed: domain models are frozen dataclasses backed
by closed-set `Enum`s, the JSON boundary is `object` with explicit narrowing
helpers, and all modules are checked with `mypy --strict` (see `mypy.ini`).
No `Any` leaks across module boundaries.

## Running the app

The application modules use `app/` as their working directory, so start
gunicorn from inside it:

```sh
cd app
../.venv/bin/gunicorn -c gunicorn.conf.py app:app
```

Then check it:

```sh
curl http://127.0.0.1:6000/healthz
curl http://127.0.0.1:6000/api/v1/status
```

## Docker

```sh
docker build -t lametric-exoscale-status .
docker run --rm -p 6000:6000 lametric-exoscale-status
```

The image listens on port `6000` and performs a `wget` health check against
`/healthz`.

## CI (GitHub Actions)

Two workflows run on push / PR to `reworking_code` and `master`:

- **`tests.yml`** — parallel jobs, all using the pinned dependencies:
  - `lint`: `ruff check app tests`
  - `typecheck`: `mypy app tests` (strict)
  - `test`: `pytest` on a Python 3.12 / 3.13 / 3.14 matrix
- **`size-label.yml`** — labels each PR with `size/XS`, `size/S`, `size/M`,
  `size/L`, `size/XL`, `size/XXL` (line-count based, Kubernetes-style) via
  [`pascalgn/size-label-action`](https://github.com/pascalgn/size-label-action).

## Contributing

Pull requests are welcome — tests are the specification, please keep them
green (`pytest` + `ruff check app tests` + `mypy app tests`).
