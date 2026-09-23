from __future__ import annotations

import json
import os
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from app.config import DATA_DIR, OAUTH_STATE_PATH, TOKEN_PATH, Settings, get_settings

# Google may omit overlapping scopes (e.g. gmail.send when gmail.modify is granted).
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")


SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]


class GoogleAuthError(RuntimeError):
    """Raised when Google OAuth is misconfigured or unavailable."""


def _client_config(settings: Settings) -> dict[str, Any]:
    if not settings.google_client_id or not settings.google_client_secret:
        raise GoogleAuthError(
            "Google OAuth is not configured. Set GOOGLE_CLIENT_ID and "
            "GOOGLE_CLIENT_SECRET in .env."
        )

    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }


def _save_credentials(credentials: Credentials) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(credentials.to_json(), encoding="utf-8")


def _load_credentials() -> Credentials | None:
    if not TOKEN_PATH.exists():
        return None

    data = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    return Credentials.from_authorized_user_info(data, SCOPES)


def _save_oauth_state(state: str, code_verifier: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OAUTH_STATE_PATH.write_text(
        json.dumps({"state": state, "code_verifier": code_verifier}),
        encoding="utf-8",
    )


def _load_oauth_state() -> dict[str, str]:
    if not OAUTH_STATE_PATH.exists():
        raise GoogleAuthError(
            "Missing OAuth login state. Click Connect Google again to restart sign-in."
        )
    return json.loads(OAUTH_STATE_PATH.read_text(encoding="utf-8"))


def _clear_oauth_state() -> None:
    if OAUTH_STATE_PATH.exists():
        OAUTH_STATE_PATH.unlink()


def build_auth_url(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    flow = Flow.from_client_config(
        _client_config(settings),
        scopes=SCOPES,
        redirect_uri=settings.google_redirect_uri,
        autogenerate_code_verifier=True,
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
    )
    if not flow.code_verifier:
        raise GoogleAuthError("Failed to generate OAuth code verifier.")

    _save_oauth_state(state=state, code_verifier=flow.code_verifier)
    return auth_url


def exchange_code(
    code: str,
    state: str | None = None,
    settings: Settings | None = None,
) -> Credentials:
    settings = settings or get_settings()
    oauth_state = _load_oauth_state()

    if state and oauth_state.get("state") and state != oauth_state["state"]:
        raise GoogleAuthError("OAuth state mismatch. Click Connect Google again.")

    flow = Flow.from_client_config(
        _client_config(settings),
        scopes=SCOPES,
        redirect_uri=settings.google_redirect_uri,
        autogenerate_code_verifier=False,
        state=oauth_state.get("state"),
    )
    flow.code_verifier = oauth_state["code_verifier"]
    # Accept the scopes Google actually grants; they can be a valid subset.
    flow.oauth2session.scope = None
    flow.fetch_token(code=code)
    credentials = flow.credentials
    _save_credentials(credentials)
    _clear_oauth_state()
    return credentials


def connect_google_desktop(settings: Settings | None = None) -> Credentials:
    """Desktop OAuth using the same redirect URI as the web app.

    Google Web clients reject InstalledAppFlow's random localhost port, which
    causes Error 400: redirect_uri_mismatch. This flow opens the browser and
    listens on the redirect URI already set in .env / Google Cloud Console.
    """
    import threading
    import time
    import webbrowser
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import parse_qs, urlparse

    settings = settings or get_settings()
    redirect = settings.google_redirect_uri
    parsed = urlparse(redirect)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"

    auth_url = build_auth_url(settings)
    result: dict[str, str | None] = {"code": None, "state": None, "error": None}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            request = urlparse(self.path)
            if request.path != path:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Not found")
                return

            params = parse_qs(request.query)
            result["code"] = (params.get("code") or [None])[0]
            result["state"] = (params.get("state") or [None])[0]
            result["error"] = (params.get("error") or [None])[0]
            body = (
                b"<html><body style='font-family:Segoe UI;background:#05070d;color:#e8f1ff;"
                b"padding:40px'><h2>Oracle Google sign-in complete</h2>"
                b"<p>You can close this tab and return to the terminal.</p></body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

    try:
        server = HTTPServer((host, port), CallbackHandler)
    except OSError as exc:
        raise GoogleAuthError(
            f"Could not listen on {redirect}. Is another app using port {port}? "
            f"Stop it, or change GOOGLE_REDIRECT_URI. ({exc})"
        ) from exc

    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    print(f"Opening Google sign-in…")
    print(f"Using redirect URI: {redirect}")
    print("If Google still says redirect_uri_mismatch, add exactly that URI in")
    print("Google Cloud Console → APIs & Services → Credentials → your OAuth client")
    print("→ Authorized redirect URIs.")
    webbrowser.open(auth_url)

    deadline = time.time() + 300
    while time.time() < deadline and result["code"] is None and result["error"] is None:
        time.sleep(0.2)
    server.server_close()

    if result["error"]:
        raise GoogleAuthError(f"Google OAuth error: {result['error']}")
    if not result["code"]:
        raise GoogleAuthError("Timed out waiting for Google sign-in.")

    return exchange_code(code=str(result["code"]), state=result["state"], settings=settings)


def get_credentials(settings: Settings | None = None) -> Credentials | None:
    settings = settings or get_settings()
    credentials = _load_credentials()
    if not credentials:
        return None

    if credentials.valid:
        return credentials

    if credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
        except Exception as exc:  # Google surfaces revoked tokens as RefreshError.
            raise GoogleAuthError(
                "Google access has expired or been revoked. Run: python oracle.py --connect-google"
            ) from exc
        _save_credentials(credentials)
        return credentials

    return None


def disconnect_google() -> None:
    if TOKEN_PATH.exists():
        TOKEN_PATH.unlink()
    _clear_oauth_state()


def _granted_scopes(credentials: Credentials | None) -> list[str]:
    if not credentials or not credentials.scopes:
        return []
    return sorted(set(credentials.scopes))


def google_status(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    configured = bool(settings.google_client_id and settings.google_client_secret)
    try:
        credentials = get_credentials(settings) if configured else None
    except GoogleAuthError:
        credentials = None
    email = None
    granted = _granted_scopes(credentials)

    if credentials:
        try:
            from googleapiclient.discovery import build

            service = build("oauth2", "v2", credentials=credentials, cache_discovery=False)
            email = service.userinfo().get().execute().get("email")
        except Exception:
            email = None

    can_read_mail = any(
        scope in granted
        for scope in (
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.modify",
            "https://mail.google.com/",
        )
    )
    can_send_mail = any(
        scope in granted
        for scope in (
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/gmail.compose",
            "https://www.googleapis.com/auth/gmail.modify",
            "https://mail.google.com/",
        )
    )
    can_use_calendar = any(
        scope in granted
        for scope in (
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/calendar.events",
        )
    )

    return {
        "configured": configured,
        "connected": bool(credentials and credentials.valid),
        "email": email,
        "scopes": granted or SCOPES,
        "can_read_mail": can_read_mail,
        "can_send_mail": can_send_mail,
        "can_use_calendar": can_use_calendar,
    }
