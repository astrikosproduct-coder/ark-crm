# Deploying ARK CRM

How to put ARK CRM on a server and keep it running. Written for whoever does the install: someone comfortable with a Linux command line, not necessarily with this codebase.

The whole application is three containers: the **database** (PostgreSQL 17), the **backend** (FastAPI) and **web** (Caddy, which serves the app, forwards `/api` to the backend, and handles HTTPS). Only `web` is reachable from outside the server.

The same steps work on an on-prem server or a cloud VM. Only `.env` changes.

---

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
- **Required fields are enforced.** Marking a field required in production means every save of a record at or past that field's stage needs it. Check what it demands before you publish.

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
