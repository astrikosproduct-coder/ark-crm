# Deploying ARK CRM

How to put ARK CRM on a server and keep it running. Written for whoever does the install: someone comfortable with a Linux command line, not necessarily with this codebase.

There are two ways to install it:

- **[The astrikos.xyz server](#the-astrikosxyz-server-crmastrikosxyz)**: pm2 and nginx, following the server's POC convention (`deployment_context.md`). This is how `crm.astrikos.xyz` runs.
- **[Docker](#docker-install)**: three containers on any Linux server.

[Updating](#updating-to-a-new-version), [changing the field register](#changing-the-field-register-in-production) and the release database apply to both.

---

## The astrikos.xyz server (crm.astrikos.xyz)

### Processes, ports and names

| | Port | Public address | pm2 name | Cloudflare |
|---|---|---|---|---|
| Frontend (built app, `serve`) | **3329** | `https://crm.astrikos.xyz:8443` | `crm_3329` | **Orange** |
| Backend (FastAPI, uvicorn) | **4329** | `https://crm-api.astrikos.xyz:8443` | `crm_be_4329` | **Gray** |
| PostgreSQL 17 | 5433 | none (bound to 127.0.0.1) | — (Docker) | — |

Add the rows to the server's port registry (`deployment_context.md` §6) before deploying:

```
crm          | 3329 | 4329 | live      (API reached through crm.astrikos.xyz/api)
crm-staging  | 3331 | 4331 | reserved  (a rehearsal copy; not set up yet)
```

**One difference from the standard POC setup.** The app has no `VITE_API_URL` and must not get one. It calls the relative path `/api`, and sign-in is a full-page redirect to `/api/auth/login` that sets a cookie on that host. So the frontend's nginx block sends `/api/` to the backend on 4329, and **people use only `crm.astrikos.xyz`**. The `crm-api` block exists to follow the convention, and passes only `/api/`, so FastAPI's `/docs` is not published. The app never calls it, and a request there has no session cookie. There is no websocket.

### Before you start

| You need | Notes |
|---|---|
| Node 24 and npm, pm2, `serve` | `npm i -g pm2 serve` |
| Python 3.13 with `venv` | to match `backend/Dockerfile` |
| Docker, or a PostgreSQL 17 on the server | the database |
| The Entra redirect URI | `https://crm.astrikos.xyz:8443/api/auth/callback`, **with** the `:8443`, added to the app registration by its owner. Sign-in fails with a Microsoft error until it is. |
| The release database file | `db_backups/ark_crm_release_<date>.dump`, from [step 5 below](#5-load-the-release-database) |

### 1. Get the code

The commands below assume the checkout is `~/ark-crm`.

```sh
cd ~
git clone https://github.com/astrikosproduct-coder/ark-crm.git
cd ark-crm
git checkout main
```

### 2. Start the database

PostgreSQL 17, reachable from this server only:

```sh
docker run -d --name crm-postgres --restart unless-stopped \
  -e POSTGRES_USER=ark -e POSTGRES_PASSWORD='<strong password, no @ : />' -e POSTGRES_DB=ark_crm \
  -p 127.0.0.1:5433:5432 \
  -v crm_postgres_data:/var/lib/postgresql/data \
  postgres:17
```

Using a PostgreSQL that's already on the server works too. Point `DATABASE_URL` at it in step 3.

### 3. Backend settings and install

```sh
cd backend
cp ../deploy/astrikos/backend.env.example .env
chmod 600 .env
# fill in .env: the database password, the three ENTRA_* values and a new SESSION_SECRET
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`APP_BASE_URL` is already `https://crm.astrikos.xyz:8443`. The port is not in `.env`: pm2 passes it in step 6.

### 4. Load the release database

Make the file on the development machine ([step 5 of the Docker install](#5-load-the-release-database)), copy it to the server, then:

```sh
docker exec -i crm-postgres pg_restore -U ark -d ark_crm --no-owner --no-privileges --exit-on-error \
  < ark_crm_release_<date>.dump
```

Do this **once**, on an empty database. Delete the file from the server afterwards.

### 5. Build the frontend

```sh
cd ../frontend
npm ci && npm run build        # → frontend/dist/
```

### 6. Start both under pm2

```sh
cd ~/ark-crm/frontend
pm2 start serve --name crm_3329 -- ./dist -s -p 3329

cd ~/ark-crm/backend
PORT=4329 pm2 start serve.py --name crm_be_4329 --interpreter "$PWD/.venv/bin/python"

pm2 save
```

`backend/serve.py` reads `PORT`, listens on 127.0.0.1 only, and trusts forwarded headers from nginx on the same machine. It needs `backend/` as its working directory to find `.env`.

### 7. nginx

Paste the two blocks from the repository into the server's files:

| Block | Paste into | Server name → port |
|---|---|---|
| [`deploy/astrikos/astrikos.conf.crm`](deploy/astrikos/astrikos.conf.crm) | `/etc/nginx/conf/astrikos.conf` | `crm.astrikos.xyz` → 3329, and `/api/` → 4329 |
| [`deploy/astrikos/astriverse.conf.crm`](deploy/astrikos/astriverse.conf.crm) | `/etc/nginx/conf/astriverse.conf` | `crm-api.astrikos.xyz/api/` → 4329; anything else 404 |

```sh
sudo nginx -t && sudo systemctl reload nginx
```

The frontend block differs from the standard one in three ways:

- the `/api/` location;
- a 25 MB upload limit and a 5-minute timeout there, for spreadsheet imports;
- cache headers: hashed `/assets/` are kept forever, and everything else is `no-cache` so a deploy reaches browsers.

### 8. Cloudflare DNS

- `crm.astrikos.xyz` → **Orange** (proxied)
- `crm-api.astrikos.xyz` → **Gray** (DNS only)

### 9. Check it

```sh
pm2 ls                                                        # crm_3329 and crm_be_4329 online
curl -k https://crm.astrikos.xyz:8443/                        # the app's HTML
curl -k https://crm.astrikos.xyz:8443/api/auth/me             # JSON "Your session has ended...", not HTML
curl -k https://crm-api.astrikos.xyz:8443/api/auth/me         # the same JSON: the backend answers directly
curl -sk -o /dev/null -w '%{http_code}\n' https://crm-api.astrikos.xyz:8443/docs   # 404: the route map is not published
curl -skI https://crm.astrikos.xyz:8443/ | grep -i cache-control   # no-cache
```

Then open `https://crm.astrikos.xyz:8443` in a browser. You're sent to Microsoft and back to the Dashboard. See [step 7 of the Docker install](#7-check-it) for what each person should see.

### Updating on this server

```sh
cd ~/ark-crm

# 1. Copy the database FIRST
docker exec crm-postgres pg_dump -U ark -Fc ark_crm > ~/crm_before_update_$(date +%Y%m%d_%H%M).dump

# 2. Get the new version. Publishing in Administration rewrites the fallback
#    files in frontend/spec on this server, so discard those first. The live app
#    reads the published version from the database, so nothing is lost.
git checkout -- frontend/spec
git pull

# 3. Install, apply database changes, rebuild, restart
backend/.venv/bin/pip install -r backend/requirements.txt
(cd backend && .venv/bin/alembic upgrade head)
(cd frontend && npm ci && npm run build)
pm2 restart crm_be_4329 crm_3329
```

Run any register script a migration names under *DEPLOY ORDER* after the `alembic` step, e.g. `(cd backend && .venv/bin/python po_received_date_metadata.py --apply)`.

---

## Docker install

The whole application is three containers: the **database** (PostgreSQL 17), the **backend** (FastAPI) and **web** (Caddy, which serves the app, forwards `/api` to the backend, and handles HTTPS). Only `web` is reachable from outside the server.

The same steps work on an on-prem server or a cloud VM. Only `.env` changes.

## Before you start

| You need | Notes |
|---|---|
| A Linux server | 2 CPU, 4 GB RAM and 20 GB disk is plenty for the first year |
| Docker Engine with the compose plugin | [docs.docker.com/engine/install](https://docs.docker.com/engine/install/) |
| A hostname, e.g. `crm.astrikos.ai` | pointing at the server |
| An HTTPS certificate | automatic if the hostname is reachable from the internet; otherwise see [Certificates from Astrikos's own CA](#certificates-from-astrikoss-own-ca) |
| The redirect URI registered in Entra | `https://<hostname>/api/auth/callback`, added by whoever owns the app registration. Sign-in fails with a Microsoft error until this is done. |
| The release database file | `db_backups/ark_crm_release_<date>.dump`. See step 5. |
| Read access to the GitHub repository | the server needs to clone it |

---

## First install

### 1. Get the code

```sh
git clone https://github.com/astrikosproduct-coder/ark-crm.git
cd ark-crm
git checkout main
```

### 2. Write the settings

```sh
cp .env.example .env
chmod 600 .env
```

Fill in `.env`. The file explains every line; the ones that matter most:

- `SITE_ADDRESS`: the hostname alone, e.g. `crm.astrikos.ai`
- `APP_BASE_URL`: the same hostname as a URL, e.g. `https://crm.astrikos.ai`, with no trailing slash
- `SESSION_HTTPS_ONLY=true`
- `POSTGRES_PASSWORD`: a new, strong password. Avoid `@ : /`.
- `SESSION_SECRET`: generate it once and keep it; changing it signs everyone out:
  ```sh
  python3 -c "import secrets; print(secrets.token_urlsafe(48))"
  ```
- The three `ENTRA_*` values: from the app registration

**Never reuse development values**, and never commit `.env`.

### 3. Build

```sh
docker compose build
```

### 4. Start the database only

```sh
docker compose up -d --wait db
```

### 5. Load the release database

Production starts with the field register and one administrator, and no business records. That starting point is made on the development machine, because the register lives only in its database:

```sh
# on the DEVELOPMENT machine
cd backend
python make_release_database.py            # dry run: shows what is kept and emptied
python make_release_database.py --write    # writes db_backups/ark_crm_release_<date>.dump
```

The script refuses to write the file unless the register is intact, every business table is empty, and the only user is the first administrator. Copy the file to the server (e.g. with `scp`), then:

```sh
# on the SERVER
docker compose exec -T db sh -c \
  'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges --exit-on-error' \
  < ark_crm_release_<date>.dump
```

Do this **once**, on an empty database. Delete the file from the server afterwards.

### 6. Start everything

```sh
docker compose up -d
```

### 7. Check it

```sh
docker compose ps                                     # three services, db "healthy"
curl -s https://<hostname>/api/auth/me                # {"detail":"Your session has ended..."}: JSON, not a web page
curl -sI https://<hostname>/ | grep -i cache-control  # no-cache
```

Then in a browser:

1. Open `https://<hostname>`. You're sent to Microsoft and back to the Dashboard.
2. The first administrator (Kishan Pawar) lands with full access, including Administration.
3. Anyone else lands on **Access pending** until a developer gives them a role in Administration. **That's expected**: a new sign-in gets no access by default.

---

## Updating to a new version

```sh
cd ark-crm

# 1. Copy the database FIRST: the one undo there is if an update goes wrong
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' \
  > ~/ark_before_update_$(date +%Y%m%d_%H%M).dump

# 2. Get the new version
git pull

# 3. Build, apply database changes, restart
docker compose build
docker compose run --rm backend alembic upgrade head
docker compose up -d
```

Keep that pre-update copy somewhere **other than this server**. Scheduled nightly backups are planned for the next phase; until then this manual copy is the only safety net.

**Read the migration notes before step 3.** A migration that changes the field register names a script to run after it, under *DEPLOY ORDER* at the top of the migration file:

```sh
docker compose run --rm backend python po_received_date_metadata.py --apply
```

---

## Changing the field register in production

**A change published in production's Administration is live.** The app loads the latest published field list from the server each time a page opens, and the server checks every save against that same version. There's no rebuild and no restart. A draft that hasn't been published changes nothing.

Two things to know:

- **Only production changes.** The development database doesn't get the edit. Make the same change there too before writing code that depends on it, or use a committed script run on both (the pattern of `pilot_po_received_date_metadata.py`).
- **Required fields are enforced.** A field made required is asked for when a record leaves that field's stage, and can't be emptied afterwards. Check what it demands before you publish.
- **People already working keep their page.** Nobody is interrupted. Within a few minutes, and on their next refused save, they see "There's a new update. Save your work, then reload to see it." Publish at quiet times, or tell the team first, when you change what's required.

A new field that needs a database column comes with a migration. Run its script after `alembic upgrade head`, as the migration's *DEPLOY ORDER* says.

---

## Certificates from Astrikos's own CA

If the server is internal-only and Let's Encrypt can't reach it, use a certificate from the company CA. Put the certificate and key on the server, e.g. in `./certs/`, then:

1. Mount them into `web` in `docker-compose.yml`:
   ```yaml
   volumes:
     - ./certs:/certs:ro
   ```
2. Add one line inside the site block of `frontend/Caddyfile`:
   ```
   tls /certs/crm.crt /certs/crm.key
   ```
3. `docker compose up -d --build web`

---

## Everyday commands

| To | Run |
|---|---|
| See what's running | `docker compose ps` |
| Read the backend log | `docker compose logs -f backend` |
| Restart one service | `docker compose restart backend` |
| Stop everything | `docker compose down` (data is kept) |
| Open a database shell | `docker compose exec db sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"'` |

**Never run `docker compose down -v`** on the server. `-v` deletes the database volume, which means every record.
