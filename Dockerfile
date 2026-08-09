# Contour — Earth Engine backend, built for Google Cloud Run.
#
# Build and deploy (see DEPLOY.md for the full walkthrough):
#   gcloud run deploy contour-api --source . --region europe-west2
#
# Cloud Run injects PORT and expects the container to listen on it on all
# interfaces. Everything else comes from environment variables and secrets.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first: editing application code below doesn't invalidate this
# layer, so rebuilds skip the whole pip install.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copied explicitly rather than `COPY . .` so a stray service-account key or
# .env in the working tree can never end up in a pushed image.
#
# This is every module the served app imports, directly or transitively. An
# omission here is not a soft failure: the module is simply absent from the
# image, so `import` raises and the container dies before it serves anything.
# tests/test_docker_context.py walks the import graph and fails if this list
# stops covering it — the list had already drifted five modules behind by the
# time anyone tried to deploy.
COPY app.py mock_ee_backend.py routes_catalog.py \
     catalog.py series.py ee_series.py \
     cache.py geometry.py redaction.py summary.py \
     open_data.py ea_hydrology.py ons_store.py insights.py nlq.py \
     ratelimit.py telemetry.py baselines.py licensing.py ./

# Don't run as root. Cloud Run doesn't require it, but nothing here needs the
# privileges and the container has network egress.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin contour
USER contour

# Cloud Run's default. Honour whatever it actually injects at runtime.
ENV PORT=8080

# Which ASGI app to serve. Point this at the mock to deploy a working API
# before Earth Engine credentials exist:
#   gcloud run deploy ... --set-env-vars APP_MODULE=mock_ee_backend:app
ENV APP_MODULE=app:app

EXPOSE 8080

# Shell form so $APP_MODULE and $PORT expand; exec so uvicorn becomes PID 1 and
# receives Cloud Run's SIGTERM directly, rather than sitting behind a shell that
# would swallow it and force a 10s kill on every scale-down.
CMD exec uvicorn "$APP_MODULE" --host 0.0.0.0 --port "$PORT"
