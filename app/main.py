from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from app.web_dashboard import router, mark_connection, failure_message, connection_state

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
app.include_router(router)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1','localhost'])


@app.middleware('http')
async def local_access(request: Request, call_next):
    origin = request.headers.get('origin')
    if origin and origin not in ('http://127.0.0.1:8000','http://localhost:8000'):
        return JSONResponse({'detail':'Cross-origin access is not allowed.'}, status_code=403)
    if request.method not in ('GET','HEAD','OPTIONS') and request.headers.get('x-oracle-request') != 'local-dashboard':
        return JSONResponse({'detail':'Use the local Oracle dashboard for this action.'}, status_code=403)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return response


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    return JSONResponse({'detail':'Oracle could not complete this action. Check local settings and try again.'}, status_code=500)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "Oracle"}


@app.get("/api/google/status", response_model=GoogleStatusResponse)
def google_status_endpoint() -> GoogleStatusResponse:
    settings = get_settings()
    status = google_status(settings)
    return GoogleStatusResponse(**status)


@app.post("/api/google/connect")
def google_connect():
    settings = get_settings()
    try:
        return {'url': build_auth_url(settings)}
    except GoogleAuthError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/google/callback")
def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    try:
        if error or not code or not state:
            raise GoogleAuthError('Sign-in cancelled or invalid callback.')
        exchange_code(code, state=state)
    except Exception:
        return RedirectResponse('/?google=failed#connections', status_code=303)
    return RedirectResponse('/?google=connected#connections', status_code=303)


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
        mark_connection('llm','error','API key missing. Open Connections to add it.')
        raise HTTPException(status_code=503, detail='API key missing. Open Connections to add it.') from None
    except LLMServiceError as exc:
        detail = failure_message(exc)
        mark_connection('llm','error',detail)
        raise HTTPException(status_code=502, detail=detail) from None

    mark_connection('llm','ready','Last chat request succeeded.')

    return ChatResponse(
        reply=reply,
        model=settings.openai_model,
        needs_confirmation=needs_confirmation,
    )
