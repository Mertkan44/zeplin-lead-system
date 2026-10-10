import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

import api.health as health_api
from scripts.check_operations import alerts
from scripts.database_backup import BackupFailed, backup, connection
from scripts.smoke_release import ProbeFailed, probe
from src.storage import supabase

SHA = 'a' * 40


class OperationsTests(unittest.TestCase):
    def client(self, *, release=SHA, expose=False, protected=False, asset_ok=True):
        def response(request):
            path = request.url.path
            if path == '/api/health':
                return httpx.Response(200, json={'ok': True, 'ready': True, 'release': release})
            if path == '/':
                return httpx.Response(200, text='<div id="root"></div><script src="/assets/main.js"></script><link href="/assets/main.css">',
                                      headers={'content-security-policy': "script-src 'self'; frame-ancestors 'none'"})
            if path.startswith('/assets/'):
                return httpx.Response(200, text='fixture', headers={'content-type': ('application/javascript' if path.endswith('.js') else 'text/css') if asset_ok else 'text/html'})
            if path == '/api/auth':
                return httpx.Response(200, json={'authenticated': False, 'user': None})
            return httpx.Response(200 if expose else 302 if protected else 401, json={'ok': expose})
        return httpx.Client(transport=httpx.MockTransport(response))

    def test_smoke_checks_release_assets_and_unauthenticated_access(self):
        with self.client() as client:
            self.assertEqual(len(probe('https://demo.example', expected_commit=SHA, client=client)), 3)

    def test_smoke_rejects_wrong_release_leaked_api_and_html_asset(self):
        for options in ({'release': 'b' * 40}, {'expose': True}, {'protected': True}, {'asset_ok': False}):
            with self.client(**options) as client, self.assertRaises(ProbeFailed):
                probe('https://demo.example', expected_commit=SHA, client=client)

    def test_smoke_rejects_credentials_and_remote_http(self):
        for url in ('http://demo.example', 'https://user:password@demo.example', 'https://demo.example/?token=private'):
            with self.assertRaises(ProbeFailed):
                probe(url)

    def test_health_exposes_only_valid_commit_and_admin_schema(self):
        handler = health_api.handler.__new__(health_api.handler)
        captured = []
        with patch.object(health_api, 'supabase_enabled', return_value=True), \
                patch.object(health_api, 'schema_status', return_value={'ready': True, 'version': '011'}), \
                patch.object(health_api, 'current_user', return_value=None), \
                patch.object(health_api, 'send_json', side_effect=lambda h,s,p,**k: captured.append((s,p))), \
                patch.dict(os.environ, {'VERCEL_GIT_COMMIT_SHA': SHA}):
            handler.do_GET()
        self.assertEqual(captured, [(200, {'ok': True, 'ready': True, 'release': SHA})])

    def test_audit_failure_is_observable_without_retry_or_sensitive_logs(self):
        class FailingClient:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def post(self, *args, **kwargs): raise RuntimeError('private key and customer@example.com')
        with patch.object(supabase, 'supabase_config', return_value=supabase.SupabaseConfig('https://demo.example', 'private-key')), \
                patch.object(supabase.httpx, 'Client', return_value=FailingClient()), \
                self.assertLogs('zeplin.operations', level='ERROR') as logs:
            supabase.insert_audit_event(actor_email='customer@example.com', event_type='lead_status_changed', target_type='lead', target_key='private name')
        output = '\n'.join(logs.output)
        self.assertIn('audit_persistence_failed', output)
        self.assertIn('RuntimeError', output)
        for secret in ('private key', 'customer@example.com', 'private name'):
            self.assertNotIn(secret, output)

    def test_connection_keeps_password_out_of_command_arguments(self):
        env, identity = connection('postgresql://demo:synthetic%40password@db.example:5432/postgres?sslmode=require')
        self.assertEqual(env['PGPASSWORD'], 'synthetic@password')
        self.assertEqual(env['PGSSLMODE'], 'require')
        self.assertEqual(len(identity), 64)
        with self.assertRaises(BackupFailed):
            connection('postgresql://demo@db.example/postgres?options=-c%20search_path=private')

    def test_backup_collision_never_removes_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'existing.dump'
            path.write_bytes(b'old backup')
            with self.assertRaises(BackupFailed):
                backup(path, {}, 'fixture')
            self.assertEqual(path.read_bytes(), b'old backup')

    def test_monitor_thresholds_and_terminal_errors(self):
        totals = {'oldest_queue_seconds': 3599, 'stalled': 0, 'failed_jobs_1h': 0,
                  'failed_generations_1h': 0, 'provider_errors_1h': 4}
        self.assertEqual(alerts(totals), [])
        for key, value in [('oldest_queue_seconds', 3601), ('stalled', 1), ('failed_jobs_1h', 1), ('failed_generations_1h', 1), ('provider_errors_1h', 5)]:
            self.assertEqual(len(alerts({**totals, key: value})), 1)


if __name__ == '__main__':
    unittest.main()
