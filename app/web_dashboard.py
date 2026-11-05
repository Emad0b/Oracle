"""Local dashboard API. Secrets are write-only; finance never goes to the LLM."""
import asyncio
import os
import threading
from pathlib import Path
from urllib.parse import urlparse

from dotenv import set_key
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from openai import AsyncOpenAI
import httpx

from app.config import get_settings
from app.finance import FinanceStore, pence
from app.google_auth import google_status, get_credentials
from app.iot import list_devices, control_device

router = APIRouter(prefix='/api')
ENV_PATH = Path(__file__).resolve().parent.parent / '.env'
settings_lock = threading.Lock()
connection_state = {}


def failure_message(exc):
    """Do not expose provider messages that may contain keys or personal data."""
    detail = str(exc).lower()
    if 'quota' in detail or '429' in detail or 'rate limit' in detail:
        return 'Provider quota or rate limit reached. Check billing/limits, then retry.'
    if '401' in detail or 'authentication' in detail or 'invalid_api_key' in detail:
        return 'API key rejected. Update your key in Connections and test again.'
    if '404' in detail or 'model_not_found' in detail:
        return 'Model or endpoint unavailable. Check the model and API URL in Connections.'
    return 'Connection failed. Check your network, credentials and provider settings, then retry.'


def mark_connection(name, status, message):
    connection_state[name] = dict(status=status, message=message)


@router.get('/connections')
async def connections():
    s = get_settings()
    llm = connection_state.get('llm', dict(status='unchecked', message='Key saved. Test the API to verify model access.')) if s.openai_api_key else dict(status='error', message='No API key configured. Add one to enable chat.')
    async def google_check():
        if not s.google_client_id or not s.google_client_secret:
            return dict(status='error', message='Google OAuth is not configured. Add your client ID and secret.')
        try:
            status = await asyncio.wait_for(asyncio.to_thread(google_status, s), 12)
            if not status['connected']:
                return dict(status='error', message='Google is disconnected or access expired. Reconnect your account.')
            if not status.get('email'):
                return dict(status='error', message='Google verification failed. Check your network or reconnect.')
            if not all(status.get(k) for k in ('can_read_mail','can_send_mail','can_use_calendar')):
                return dict(status='error', message='Some Gmail or Calendar permissions are missing. Reconnect and grant access.')
            credentials = await asyncio.to_thread(get_credentials, s)
            if not credentials:
                return dict(status='error', message='Google session expired. Reconnect your account.')
            async with httpx.AsyncClient(timeout=8) as client:
                checks = await asyncio.gather(*[
                    client.get(url, headers={'Authorization': 'Bearer ' + credentials.token})
                    for url in ('https://gmail.googleapis.com/gmail/v1/users/me/profile',
                                'https://www.googleapis.com/calendar/v3/users/me/calendarList?maxResults=1')
                ])
            if any(response.status_code in (401,403) for response in checks):
                return dict(status='error', message='Gmail or Calendar access was rejected. Enable both APIs in Google Cloud, then reconnect and grant permissions.')
            if any(response.status_code != 200 for response in checks):
                return dict(status='error', message='Gmail or Calendar is unavailable or rate limited. Wait and check again.')
            return dict(status='ready', message='Google account connected. Gmail and Calendar permissions granted.')
        except Exception:
            return dict(status='error', message='Google connection could not be checked. Retry or reconnect.')
    async def device_check():
        try:
            result = await asyncio.wait_for(asyncio.to_thread(list_devices), 12)
            return dict(status='demo' if result['simulated'] else 'ready', message='Simulated devices — no hardware connected.' if result['simulated'] else 'Home Assistant is reachable.')
        except Exception:
            return dict(status='error', message='Home Assistant is unreachable. Check its URL, token and allowed entities.')
    google, iot = await asyncio.gather(google_check(), device_check())
    return dict(llm=dict(llm, model=s.openai_model), google=google, iot=iot,
                configuration=dict(model=s.openai_model, base_url=s.openai_base_url or '',
                                   redirect_uri=s.google_redirect_uri, iot_backend=os.getenv('IOT_BACKEND','demo')))


class Configuration(BaseModel):
    provider: str
    values: dict[str, str] = Field(default_factory=dict, max_length=8)


@router.post('/connections/configure')
def configure(payload: Configuration):
    allowed = {
        'llm': {'OPENAI_API_KEY','OPENAI_MODEL','OPENAI_BASE_URL'},
        'google': {'GOOGLE_CLIENT_ID','GOOGLE_CLIENT_SECRET','GOOGLE_REDIRECT_URI'},
        'iot': {'IOT_BACKEND','HA_URL','HA_TOKEN','HA_ALLOWED_ENTITIES'},
    }
    if payload.provider not in allowed or not set(payload.values) <= allowed[payload.provider]:
        raise HTTPException(400, 'Unsupported setting.')
    for key, value in payload.values.items():
        if len(value) > 4096 or any(c in value for c in '\r\n\x00'):
            raise HTTPException(400, 'Invalid setting value.')
        if key.endswith('URL') and value:
            parsed = urlparse(value)
            if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
                raise HTTPException(400, 'Enter an HTTP(S) URL without embedded credentials.')
            if key == 'OPENAI_BASE_URL' and parsed.scheme != 'https' and parsed.hostname not in ('localhost','127.0.0.1','::1'):
                raise HTTPException(400, 'Use HTTPS for remote AI providers to protect your key.')
        if key == 'GOOGLE_REDIRECT_URI' and value not in ('http://127.0.0.1:8000/api/google/callback','http://localhost:8000/api/google/callback'):
            raise HTTPException(400, 'Use http://127.0.0.1:8000/api/google/callback and register it in Google Cloud.')
        if key == 'IOT_BACKEND' and value not in ('demo','home_assistant'):
            raise HTTPException(400, 'Choose demo or home_assistant.')
    try:
        with settings_lock:
            for key, value in payload.values.items():
                # Blank secrets keep existing values; blank base URL restores default.
                if not value and key != 'OPENAI_BASE_URL':
                    continue
                set_key(str(ENV_PATH), key, value)
                os.environ[key] = value
    except OSError:
        raise HTTPException(500, 'Could not save local settings. Check .env permissions.') from None
    connection_state.pop(payload.provider, None)
    return {'saved': True}


@router.post('/connections/test-llm')
async def test_llm():
    s = get_settings()
    if not s.openai_api_key:
        mark_connection('llm','error','Add an API key before testing.')
    else:
        try:
            async with AsyncOpenAI(api_key=s.openai_api_key, base_url=s.openai_base_url, timeout=15, max_retries=0) as client:
                # Real inference verifies quota and model access, not just a key's presence.
                await client.chat.completions.create(model=s.openai_model, messages=[{'role':'user','content':'Reply OK.'}], max_completion_tokens=8)
            mark_connection('llm','ready','Model responded successfully. Chat is ready.')
        except Exception as exc:
            mark_connection('llm','error',failure_message(exc))
    return connection_state['llm']


@router.get('/devices')
def devices():
    try:
        return list_devices()
    except Exception:
        raise HTTPException(503, 'Device connection failed. Open Connections to update Home Assistant.') from None


class DeviceAction(BaseModel):
    entity_id: str
    action: str


@router.post('/devices/control')
def device_action(payload: DeviceAction):
    try:
        return control_device(payload.entity_id, payload.action)
    except ValueError:
        raise HTTPException(400, 'Could not control this device. Check its allowlist and connection.') from None


@router.get('/money')
def money_dashboard():
    store = FinanceStore()
    return dict(summary=store.summary(), settings=store.settings(), transactions=store.transactions(), schedules=store.schedules(),
                pots=store.pots(), movements=store.movements(), forecast=store.forecast())


class MoneyAction(BaseModel):
    action: str
    values: dict = Field(default_factory=dict, max_length=12)


@router.post('/money')
def money_action(payload: MoneyAction):
    s = FinanceStore(); v = payload.values
    try:
        if payload.action == 'settings':
            s.configure(v['payday'], pence(v['buffer']), pence(v['warning']))
        elif payload.action == 'reconcile':
            s.reconcile(pence(v['balance']))
        elif payload.action == 'transaction':
            s.transaction(v['name'], pence(v['amount']), v['day'], v['category'], int(v['id']) if v.get('id') else None)
        elif payload.action == 'delete_transaction':
            s.delete_transaction(int(v['id']))
        elif payload.action == 'schedule':
            s.add_schedule(v['name'], pence(v['amount']), v['kind'], v['start'], v['frequency'], v['category'], v.get('estimated') == 'yes')
        elif payload.action == 'stop_schedule':
            s.stop_schedule(int(v['id']))
        elif payload.action == 'settle':
            s.settle(int(v['id']), v['due'])
        elif payload.action == 'pot':
            s.add_pot(v['name'], pence(v['target']), v.get('target_date'))
        elif payload.action == 'move_pot':
            s.move_pot(int(v['id']), pence(v['amount']))
        else:
            raise ValueError('Unknown finance action.')
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(400, str(exc) if isinstance(exc, ValueError) else 'Check the required fields.') from None
    return {'saved': True}
