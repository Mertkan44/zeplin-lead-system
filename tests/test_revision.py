import json
import unittest
from contextlib import ExitStack
from datetime import datetime, timezone
from unittest.mock import patch

import httpx

from api import assignments, outreach, workspace
from src.ai import cache
from src.ai.generator import ai_input_fingerprint
from src.integrations.google_places import select_best_candidate
from src.research import research_website
from src.workflow import build_team_performance
from src.storage import supabase


class RevisionTests(unittest.TestCase):
    def test_archived_assignment_does_not_grant_workspace_read(self):
        with ExitStack() as stack:
            fixtures = {
                'require_auth': {'sub': 'old@example.test', 'role': 'sales'},
                'supabase_enabled': True,
                'fetch_leads_full': [{'name': 'Synthetic lead'}],
                'fetch_lead_assignments': [],
                'fetch_outreach_events': [],
                'build_team_performance': [],
                'places_configured': False,
            }
            for name, value in fixtures.items():
                stack.enter_context(patch.object(workspace, name, return_value=value))
            response = stack.enter_context(patch.object(workspace, 'send_json'))
            workspace.handler.do_GET(object())
            self.assertEqual(response.call_args.args[2]['leads'], [])
            self.assertEqual(workspace.fetch_lead_assignments.call_args.kwargs['status'], 'active')

    def test_archived_assignment_cannot_be_reactivated_by_sales(self):
        with ExitStack() as stack:
            fixtures = {
                'require_auth': {'sub': 'old@example.test', 'role': 'sales'},
                'read_json': {'id': 7, 'status': 'active'},
                'fetch_lead_assignment_by_id': {'id': 7, 'user_email': 'old@example.test', 'status': 'archived'},
            }
            for name, value in fixtures.items():
                stack.enter_context(patch.object(assignments, name, return_value=value))
            update = stack.enter_context(patch.object(assignments, 'update_lead_assignment'))
            response = stack.enter_context(patch.object(assignments, 'send_json'))
            assignments.handler.do_PATCH(object())
            self.assertEqual(response.call_args.args[1], 403)
            update.assert_not_called()

    def test_ai_cache_uses_remote_when_local_file_is_read_only(self):
        with patch.object(cache, 'load_cache', return_value={}), \
             patch.object(cache, 'save_cache', side_effect=OSError('read only')), \
             patch('src.storage.supabase.upsert_ai_generation') as remote:
            cache.put('test-key', task='report', provider='test', model='test', content='generated')
            remote.assert_called_once()

    def test_research_rejects_private_redirect_before_request(self):
        requested = []
        def transport(request):
            requested.append(str(request.url))
            return httpx.Response(302, headers={'location': 'http://127.0.0.1/private'})
        real_client = httpx.Client
        def safety(url):
            if '127.0.0.1' in url:
                raise ValueError('private URL')
            return url
        with patch('src.research.assert_safe_public_url', side_effect=safety), \
             patch('src.research.httpx.Client', side_effect=lambda **kw: real_client(transport=httpx.MockTransport(transport), **kw)):
            result = research_website('https://public.example.test')
        self.assertEqual(result['status'], 'error')
        self.assertEqual(requested, ['https://public.example.test'])

    def test_places_rejects_same_name_in_another_city(self):
        result = select_best_candidate(
            {'name': 'Synthetic Cafe', 'city': 'Ankara'},
            [{'id': 'wrong', 'displayName': {'text': 'Synthetic Cafe'}, 'formattedAddress': 'Izmir'}],
        )
        self.assertIsNone(result)

    def test_istanbul_day_boundary_applies_to_team_metrics(self):
        result = build_team_performance([], [{
            'lead_name': 'Synthetic lead', 'actor_email': 'sales@example.test',
            'action': 'contact_result_recorded', 'channel': 'phone',
            'happened_at': '2026-09-29T12:00:00+00:00',
        }], now=datetime(2026, 9, 29, 22, 30, tzinfo=timezone.utc))
        self.assertEqual(result[0]['calls_today'], 0)

    def test_ai_fingerprint_changes_with_findings(self):
        lead = {'name': 'Synthetic lead', 'audit_findings': [{'code': 'old'}]}
        first = ai_input_fingerprint(lead)
        lead['audit_findings'] = [{'code': 'new'}]
        self.assertNotEqual(first, ai_input_fingerprint(lead))

    def test_outreach_api_delegates_status_change_to_atomic_rpc(self):
        with ExitStack() as stack:
            fixtures = {
                'require_auth': {'sub': 'admin@example.test', 'role': 'admin'},
                'supabase_enabled': True,
                'require_lead_access': None,
                'read_json': {'lead_name': 'Synthetic lead', 'action': 'contact_result_recorded',
                              'channel': 'phone', 'outcome': 'won', 'idempotency_key': 'retry-key'},
                'record_outreach_action': {'inserted': True, 'event': {'lead_name': 'Synthetic lead', 'action': 'contact_result_recorded'}},
            }
            for name, value in fixtures.items():
                stack.enter_context(patch.object(outreach, name, return_value=value))
            response = stack.enter_context(patch.object(outreach, 'send_json'))
            outreach.handler.do_POST(object())
            self.assertEqual(response.call_args.args[1], 200)
            self.assertEqual(outreach.record_outreach_action.call_args.kwargs['status'], 'converted')
            self.assertEqual(outreach.record_outreach_action.call_args.kwargs['assignment_status'], 'done')

    def test_atomic_rpc_payload_keeps_idempotency_key(self):
        requests = []
        def transport(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, json={'inserted': False, 'event': {'id': 1}})
        real_client = httpx.Client
        with patch.object(supabase, 'supabase_config', return_value=supabase.SupabaseConfig('https://example.test', 'test-key')), \
             patch.object(supabase.httpx, 'Client', side_effect=lambda **kw: real_client(transport=httpx.MockTransport(transport), **kw)):
            result = supabase.record_outreach_action(lead_name='Synthetic lead', action='deal_won', note=None,
                happened_at=None, actor_email='admin@example.test', source='test', idempotency_key='retry-key', status='converted')
        self.assertFalse(result['inserted'])
        self.assertEqual(requests[0]['target_idempotency_key'], 'retry-key')
        self.assertEqual(requests[0]['target_status'], 'converted')

    def test_passwords_need_minimum_length(self):
        from src.auth import make_password_hash
        with self.assertRaises(ValueError):
            make_password_hash('short')
        self.assertTrue(make_password_hash('long enough passphrase'))

    def test_manual_verification_expires_after_30_days(self):
        from src.workflow import build_lead_workflow
        lead = {
            'name': 'Synthetic lead', 'category': 'Clinic', 'phone': '02120000000',
            'manual_verification': {
                'checked_at': '2026-08-01T00:00:00+00:00',
                'google': {'checked': True, 'status': 'found'},
                'instagram': {'checked': True, 'status': 'not_found'},
                'website': {'checked': True, 'status': 'working'},
            },
        }
        self.assertFalse(build_lead_workflow(lead, now=datetime(2026, 9, 1, tzinfo=timezone.utc))['ready_to_contact'])

    def test_durable_limiter_failure_blocks_login(self):
        from src.auth import login_rate_limited
        with patch('src.auth.supabase.check_login_rate_limit', return_value=None), \
             patch('src.auth.supabase.is_enabled', return_value=True):
            with self.assertRaises(RuntimeError):
                login_rate_limited('test:account')


if __name__ == '__main__':
    unittest.main()
