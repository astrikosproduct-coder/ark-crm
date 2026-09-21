# ARK CRM frontend — built once, then served by Caddy, which also forwards /api
# to the backend and handles HTTPS.
#
# Build from the REPOSITORY ROOT (docker-compose.yml does this):
#     docker build -f frontend/Dockerfile .
#
# The built app contains NO addresses or settings: every call goes to the
# relative path /api, so the same image serves any hostname. Never introduce a
# VITE_API_URL — Vite bakes it in at build time and the image stops being
# portable.

# ---- 1. build
FROM node:24-alpine AS build
WORKDIR /srv/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

# ---- 2. serve
FROM caddy:2-alpine
COPY frontend/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /srv/frontend/dist /srv/www
