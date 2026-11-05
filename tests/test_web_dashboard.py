import importlib
import gc
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient
from app.main import app
from app.finance import FinanceStore
from app import web_dashboard


HEADERS={'X-Oracle-Request':'local-dashboard','Origin':'http://127.0.0.1:8000'}


class WebTests(unittest.TestCase):
    def setUp(self):
        # Dispose prior Tk test widgets on the main thread before ASGI workers start.
        gc.collect()
        self.client=TestClient(app,base_url='http://127.0.0.1:8000')
        web_dashboard.connection_state.clear()

    def test_full_application_imports(self):
        # Regression: GoogleServiceError was deleted while tools still imported it.
        from app.google_services import GoogleServiceError
        self.assertTrue(issubclass(GoogleServiceError,RuntimeError))
        self.assertTrue(hasattr(importlib.import_module('app.assistant'),'OracleAssistant'))

    def test_shell_and_assets(self):
        response=self.client.get('/')
        self.assertEqual(response.status_code,200)
        self.assertIn('Everything in sync.',response.text)
        self.assertIn("frame-ancestors 'none'",response.headers['content-security-policy'])
        for asset in ('app.js','styles.css'):
            self.assertEqual(self.client.get('/static/'+asset).status_code,200)

    def test_rejects_cross_origin_mutation_and_foreign_host(self):
        self.assertEqual(self.client.post('/api/money',json={'action':'reconcile','values':{'balance':'1'}}).status_code,403)
        self.assertEqual(self.client.post('/api/google/disconnect',headers={**HEADERS,'Origin':'https://untrusted.example'},json={}).status_code,403)
        self.assertEqual(self.client.get('/api/money',headers={'Host':'untrusted.example'}).status_code,400)

    def test_missing_connections_do_not_crash_dashboard(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'','GOOGLE_CLIENT_ID':'','GOOGLE_CLIENT_SECRET':'','IOT_BACKEND':'demo'}):
            response=self.client.get('/api/connections')
        data=response.json()
        self.assertEqual(response.status_code,200)
        self.assertEqual(data['llm']['status'],'error')
        self.assertEqual(data['google']['status'],'error')
        self.assertEqual(data['iot']['status'],'demo')

    def test_chat_error_is_redacted_and_persisted_in_status(self):
        from app.llm import LLMServiceError
        with patch('app.main.generate_chat_reply',new=AsyncMock(side_effect=LLMServiceError('401 secret-value'))):
            response=self.client.post('/api/chat',headers=HEADERS,json={'message':'Hello'})
        self.assertEqual(response.status_code,502)
        self.assertNotIn('secret-value',response.text)
        self.assertEqual(web_dashboard.connection_state['llm']['status'],'error')

    def test_google_callback_failure_returns_dashboard(self):
        response=self.client.get('/api/google/callback?error=access_denied',follow_redirects=False)
        self.assertEqual(response.status_code,303)
        self.assertEqual(response.headers['location'],'/?google=failed#connections')
        with patch('app.main.exchange_code') as exchange:
            self.client.get('/api/google/callback?code=test',follow_redirects=False)
            exchange.assert_not_called()

    def test_google_reconnect_returns_authorization_url(self):
        with patch('app.main.build_auth_url',return_value='https://accounts.google.com/test'):
            response=self.client.post('/api/google/connect',headers=HEADERS,json={})
        self.assertEqual(response.json()['url'],'https://accounts.google.com/test')

    def test_revoked_google_shows_reconnect(self):
        with patch.dict(os.environ,{'GOOGLE_CLIENT_ID':'test','GOOGLE_CLIENT_SECRET':'test','IOT_BACKEND':'demo'}), patch.object(web_dashboard,'google_status',return_value={'connected':False}):
            data=self.client.get('/api/connections').json()
        self.assertEqual(data['google']['status'],'error')
        self.assertIn('Reconnect',data['google']['message'])

    def test_google_api_rejection_is_not_reported_as_connected(self):
        status=dict(connected=True,email='test@example.org',can_read_mail=True,can_send_mail=True,can_use_calendar=True)
        remote=AsyncMock()
        remote.get.return_value=Mock(status_code=403)
        manager=AsyncMock()
        manager.__aenter__.return_value=remote
        with patch.dict(os.environ,{'GOOGLE_CLIENT_ID':'test','GOOGLE_CLIENT_SECRET':'test','IOT_BACKEND':'demo'}), patch.object(web_dashboard,'google_status',return_value=status), patch.object(web_dashboard,'get_credentials',return_value=Mock(token='test')), patch.object(web_dashboard.httpx,'AsyncClient',return_value=manager):
            data=self.client.get('/api/connections').json()
        self.assertEqual(data['google']['status'],'error')
        self.assertIn('Enable both APIs',data['google']['message'])

    def test_api_quota_test_surfaces_actionable_error(self):
        remote=AsyncMock()
        remote.chat.completions.create.side_effect=RuntimeError('429 insufficient_quota secret-data')
        manager=AsyncMock()
        manager.__aenter__.return_value=remote
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test'}), patch.object(web_dashboard,'AsyncOpenAI',return_value=manager):
            response=self.client.post('/api/connections/test-llm',headers=HEADERS,json={})
        self.assertEqual(response.json()['status'],'error')
        self.assertIn('billing',response.json()['message'])
        self.assertNotIn('secret-data',response.text)

    def test_config_stays_local_and_secrets_never_echo(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(web_dashboard,'ENV_PATH',Path(temp)/'.env'), patch.dict(os.environ,{},clear=False):
            response=self.client.post('/api/connections/configure',headers=HEADERS,json={'provider':'llm','values':{'OPENAI_API_KEY':'test-private-value','OPENAI_MODEL':'example-model'}})
            self.assertEqual(response.status_code,200)
            self.assertNotIn('test-private-value',response.text)
            self.assertIn('test-private-value',(Path(temp)/'.env').read_text())
            response=self.client.post('/api/connections/configure',headers=HEADERS,json={'provider':'llm','values':{'UNEXPECTED':'bad'}})
            self.assertEqual(response.status_code,400)

    def test_finance_api_reuses_existing_database(self):
        with tempfile.TemporaryDirectory() as temp:
            store=FinanceStore(Path(temp)/'test.sqlite3')
            with patch.object(web_dashboard,'FinanceStore',return_value=store):
                response=self.client.post('/api/money',headers=HEADERS,json={'action':'reconcile','values':{'balance':'3000.00'}})
                self.assertEqual(response.status_code,200)
                data=self.client.get('/api/money').json()
                self.assertEqual(data['summary']['balance'],300000)
                self.assertEqual(len(data['transactions']),1)
                response=self.client.post('/api/money',headers=HEADERS,json={'action':'schedule','values':{'name':'Bill','amount':'-1','kind':'bill','start':'2026-12-01','frequency':'monthly','category':'Test'}})
                self.assertEqual(response.status_code,400)

    def test_launcher_defaults_to_web_without_creating_assistant(self):
        from oracle import main
        with patch('app.web_launcher.run_web',return_value=0) as run:
            self.assertEqual(main([]),0)
            run.assert_called_once_with('',open_browser=True)
        with patch('app.web_launcher.run_web',return_value=0) as run:
            self.assertEqual(main(['--money','--no-browser']),0)
            run.assert_called_once_with('money',open_browser=False)
