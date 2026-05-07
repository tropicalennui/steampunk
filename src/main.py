import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from db import DB_PATH, init_db, load_secrets  # DB_PATH re-exported for conftest compatibility
from shared import secrets, templates, STATIC_DIR, SRC_DIR, LOGS_DIR, MAX_LOG_FILES, _LOG_GLOB, _URL_WIZARD_STEAM_API

from routers import auth as auth_router
from routers import library as library_router
from routers import sync as sync_router
from routers import setup as setup_router

# ---------------------------------------------------------------------------
# Patchable shared state — accessed by routers via sys.modules["main"]
# ---------------------------------------------------------------------------

_sync_lock    = threading.Lock()
_sync_running = False


def _user(request: Request):
    return request.session.get("user")


def _run_sync(platforms: list[str] | None = None):
    global _sync_running
    with _sync_lock:
        _sync_running = True
    try:
        LOGS_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M-%S")
        log_path  = LOGS_DIR / f"sync_{timestamp}.log"
        cmd = [sys.executable, "-u", str(SRC_DIR / "collect.py")]
        if platforms:
            cmd += ["--platforms"] + platforms
        with open(log_path, "w") as log:
            log.write(f"Sync started at {timestamp} UTC\n")
            if platforms:
                log.write(f"Platforms: {', '.join(platforms)}\n")
            log.write(f"{'='*60}\n")
            log.flush()
            subprocess.run(cmd, cwd=str(SRC_DIR), stdout=log, stderr=log, text=True)
    finally:
        with _sync_lock:
            _sync_running = False
        _trim_logs()


def _trim_logs() -> None:
    if not LOGS_DIR.exists():
        return
    for old in sorted(LOGS_DIR.glob(_LOG_GLOB), reverse=True)[MAX_LOG_FILES:]:
        old.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Wizard gate middleware
# ---------------------------------------------------------------------------

class _WizardGate(BaseHTTPMiddleware):
    _OPEN_PREFIXES = ("/wizard", "/auth/", "/static/", "/favicon")

    async def dispatch(self, request, call_next):
        path = request.url.path
        if path == "/" or any(path.startswith(p) for p in self._OPEN_PREFIXES):
            return await call_next(request)
        fresh = load_secrets()
        if not fresh.get("steam", {}).get("api_key"):
            return RedirectResponse(_URL_WIZARD_STEAM_API, status_code=302)
        return await call_next(request)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

init_db()

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=secrets["app"]["session_secret"])
app.add_middleware(_WizardGate)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(auth_router.router)
app.include_router(library_router.router)
app.include_router(sync_router.router)
app.include_router(setup_router.router)
