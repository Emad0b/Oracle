from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.google_auth import (
    GoogleAuthError,
    build_auth_url,
    disconnect_google,
    exchange_code,
    google_status,
)
from app.llm import LLMServiceError, MissingApiKeyError, generate_chat_reply
from app.schemas import ChatRequest, ChatResponse, GoogleStatusResponse


BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="Oracle",
    description="Operational Resource for Analysis, Communication, and Logical Execution",
    version="0.2.0",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "Oracle"}


@app.get("/api/google/status", response_model=GoogleStatusResponse)
async def google_status_endpoint() -> GoogleStatusResponse:
    settings = get_settings()
    status = google_status(settings)
    return GoogleStatusResponse(**status)


@app.get("/api/google/connect")
async def google_connect() -> RedirectResponse:
    settings = get_settings()
    try:
        return RedirectResponse(build_auth_url(settings))
    except GoogleAuthError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/google/callback")
async def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    if error:
        raise HTTPException(status_code=400, detail=f"Google OAuth error: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing OAuth code from Google.")

    try:
        exchange_code(code, state=state)
    except GoogleAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Google OAuth failed: {exc}") from exc

    return RedirectResponse("/")


@app.post("/api/google/disconnect")
async def google_disconnect() -> dict[str, bool]:
    disconnect_google()
    return {"disconnected": True}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    settings = get_settings()

    try:
        reply, needs_confirmation = await generate_chat_reply(request, settings)
    except MissingApiKeyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ChatResponse(
        reply=reply,
        model=settings.openai_model,
        needs_confirmation=needs_confirmation,
    )
