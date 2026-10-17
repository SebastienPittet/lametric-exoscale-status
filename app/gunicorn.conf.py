"""Hardened gunicorn configuration for lametric-exoscale-status."""

wsgi_app = "app:app"

bind = "0.0.0.0:6000"

workers = 2
threads = 2

timeout = 30
graceful_timeout = 10
keepalive = 5

# Recycle workers to bound memory growth.
max_requests = 500
max_requests_jitter = 50

# Limit request size (mitigate abuse / memory pressure).
limit_request_line = 8190
limit_request_field_size = 8190
limit_request_fields = 100

loglevel = "info"
