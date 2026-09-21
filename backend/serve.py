"""Start the backend for pm2 on the astrikos.xyz server — see DEPLOY.md.

    cd backend
    PORT=4329 pm2 start serve.py --name crm_be_4329 --interpreter "$PWD/.venv/bin/python"

The port comes from the environment, never from this file, so the same entry
serves any slot in the server's port registry. It listens on 127.0.0.1 only:
nginx on the same machine is the one way in, and it terminates HTTPS and says so
in X-Forwarded-Proto. Trusting forwarded headers from 127.0.0.1 alone is what
lets the session cookie be marked Secure without trusting anybody else.

Settings (DATABASE_URL, ENTRA_*, SESSION_SECRET, APP_BASE_URL, ...) are read
from backend/.env by app/database.py, so pm2 must start this with backend/ as
its working directory. The Docker image does not use this file; it runs
uvicorn directly (backend/Dockerfile).
"""

import os

import uvicorn

if __name__ == "__main__":
    port = os.getenv("PORT")
    if not port:
        raise SystemExit("PORT is not set. Start with: PORT=<port> pm2 start serve.py ...")

    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(port),
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
    )
