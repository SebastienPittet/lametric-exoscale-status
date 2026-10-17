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
├── config.toml             # static configuration (never contains the API key)
├── gunicorn.conf.py        # hardened gunicorn settings
└── lib/
    ├── models.py           # domain models (Status, Service, Zone, Notice, StatusData)
    ├── configuration.py    # TOML config loading + optional STATUSPAL_API_KEY from the env
    ├── statuspal_parser.py # StatusPal v2 public summary payload -> domain models
    ├── statuspal_client.py # HTTP client with retry/backoff (public API, optional Bearer key)
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
request timeout, cache TTL, rate limit, LAMETRIC app name/logo and the status
icons.

The StatusPal API (v2) is public open data: **no API key is required**. If you
set the optional `STATUSPAL_API_KEY` environment variable, the key is sent as
a Bearer token. The key is **never stored in the repository** and the
configuration loads fine without it.

## Security

- Sliding-window rate limit per client IP (default 120 req/min, `429` when exceeded)
- 30 s response cache, single-flight upstream fetch (no request storms)
- Security headers on every response (`nosniff`, `DENY`, `no-referrer`, `no-store`)
- Optional API key only from the environment, never logged, never in config files
- Hardened gunicorn (request line/field size and count limits, worker recycling)
- Docker image runs as a non-root user
- JSON-only error handlers (no traceback leakage)

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt

.venv/bin/pytest -q
.venv/bin/ruff check app tests
```

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

## Contributing

Pull requests are welcome — tests are the specification, please keep them
green (`pytest` + `ruff check app tests`).
