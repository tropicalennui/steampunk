"""Sync trigger, log viewer, and log management routes."""
import asyncio
import sys

from fastapi import APIRouter, BackgroundTasks, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
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
    initial_offset = 0
    if selected:
        content = await asyncio.to_thread(lambda: (LOGS_DIR / selected).read_bytes())
        lines = content.decode("utf-8", errors="replace").splitlines(True)
        initial_offset = len(content)

    return templates.TemplateResponse(request, "logs.html", {
        "user":           user,
        "log_files":      file_names,
        "selected":       selected,
        "lines":          lines,
        "sync_running":   sys.modules["main"]._sync_running,
        "initial_offset": initial_offset,
    })


@router.get("/logs/tail")
async def logs_tail(request: Request, file: str = "", offset: int = 0):
    if not _user(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    log_files = sorted(LOGS_DIR.glob(_LOG_GLOB), reverse=True) if LOGS_DIR.exists() else []
    file_names = [f.name for f in log_files]
    if file in file_names:
        target = file
    elif file_names:
        target = file_names[0]
    else:
        target = None

    content = ""
    new_offset = offset
    if target:
        def _read():
            path = LOGS_DIR / target
            with open(path, "rb") as f:
                f.seek(offset)
                chunk = f.read()
            return chunk
        chunk = await asyncio.to_thread(_read)
        content = chunk.decode("utf-8", errors="replace")
        new_offset = offset + len(chunk)

    return JSONResponse({
        "content": content,
        "offset": new_offset,
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
