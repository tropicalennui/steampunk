"""Sync trigger, log viewer, and log management routes."""
import asyncio
import sys

from fastapi import APIRouter, BackgroundTasks, Form, Request
from fastapi.responses import RedirectResponse
from typing import Annotated

from shared import templates, LOGS_DIR, MAX_LOG_FILES, _LOG_GLOB

router = APIRouter()


def _user(request: Request):
    return sys.modules["main"]._user(request)


@router.post("/sync")
async def sync(
    request: Request,
    background_tasks: BackgroundTasks,
    platforms: Annotated[str, Form()] = "all",
):
    if not _user(request):
        return RedirectResponse("/", status_code=302)
    m = sys.modules["main"]
    if not m._sync_running:
        platform_list = None if platforms == "all" else [p.strip() for p in platforms.split(",")]
        background_tasks.add_task(m._run_sync, platform_list)
    return RedirectResponse("/logs", status_code=302)


@router.get("/logs")
async def logs_page(request: Request, file: str = ""):
    user = _user(request)
    if not user:
        return RedirectResponse("/", status_code=302)

    log_files  = sorted(LOGS_DIR.glob(_LOG_GLOB), reverse=True) if LOGS_DIR.exists() else []
    file_names = [f.name for f in log_files]

    if file in file_names:
        selected = file
    elif file_names:
        selected = file_names[0]
    else:
        selected = None

    lines: list[str] = []
    if selected:
        lines = await asyncio.to_thread(lambda: (LOGS_DIR / selected).read_text().splitlines(True))

    return templates.TemplateResponse(request, "logs.html", {
        "user":         user,
        "log_files":    file_names,
        "selected":     selected,
        "lines":        lines,
        "sync_running": sys.modules["main"]._sync_running,
    })


@router.post("/logs/clear")
async def logs_clear(request: Request):
    if not _user(request):
        return RedirectResponse("/", status_code=302)
    m = sys.modules["main"]
    if not m._sync_running and LOGS_DIR.exists():
        for f in LOGS_DIR.glob(_LOG_GLOB):
            f.unlink(missing_ok=True)
    return RedirectResponse("/logs", status_code=302)
