# ARK CRM backend — FastAPI on uvicorn.
#
# Build from the REPOSITORY ROOT (docker-compose.yml does this):
#     docker build -f backend/Dockerfile .
# because the backend reads frontend/spec at run time — extensions.json and the
# price book for spreadsheets — and writes the register's JSON there when
# someone publishes. app/metadata_spec.py finds it at ../frontend/spec relative
# to backend/, so the image keeps that layout: /srv/backend and /srv/frontend/spec.
#
# No configuration is baked in. Every setting arrives as an environment
# variable (see backend/.env.example and DEPLOY.md), so one image runs anywhere.

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/backend

# Dependencies first, so a code change does not reinstall them.
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

COPY backend/ ./
COPY frontend/spec/ /srv/frontend/spec/

# Never run as root. The spec folder is the one place the app writes.
RUN useradd --system --uid 10001 --home-dir /srv ark \
    && chown -R ark /srv/frontend/spec
USER ark

EXPOSE 8000

# --proxy-headers: the app sits behind Caddy, which terminates HTTPS and says so
# in X-Forwarded-Proto. Only Caddy can reach this port (see docker-compose.yml),
# so trusting every forwarder is safe here and nowhere else.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
