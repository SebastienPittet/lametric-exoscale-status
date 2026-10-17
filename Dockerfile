# syntax=docker/dockerfile:1

# Alpine keeps the image small (~70 MB total); 3.14 is the newest Python
# covered by the CI matrix. `python:3.14-alpine` is a moving tag: every
# rebuild picks up the latest 3.14.x, and Dependabot proposes newer
# -alpine majors as they are released.
FROM python:3.14-alpine

# Unbuffered stdout so log collectors see lines immediately; no .pyc
# churn in the runtime layer.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install dependencies before the app code so this heavy layer stays
# cached as long as requirements.txt is unchanged.
COPY requirements.txt ./
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

COPY app/ ./

# Run as an unprivileged user.
RUN addgroup -S appgroup \
    && adduser -S appuser -G appgroup \
    && chown -R appuser:appgroup /app
USER appuser

EXPOSE 6000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1:6000/healthz || exit 1

# Explicit config + app module (no reliance on gunicorn's auto-loading).
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:app"]
