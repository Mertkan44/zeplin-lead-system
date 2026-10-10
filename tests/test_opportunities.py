import io
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import api.workspace as workspace_api
from src.metrics import build_metrics
from src.opportunities import command
from src.storage import supabase

KEY = '11111111-1111-4111-8111-111111111111'
USER = {'sub': 'sales@example.com', 'role': 'sales'}


class OpportunityTests(unittest.TestCase):
    def body(self, **values):
        return {'idempotency_key': KEY, 'lead_id': 101, 'expected_lead_revision': 0,
                'expected_opportunity_revision': 0, 'stage': 'new', 'note': '',
                'amount': None, 'amount_unknown': True, 'service_slug': None, **values}

    def post(self, body, *, user=USER, error=None):
        handler = workspace_api.handler.__new__(workspace_api.handler)
        handler.path = '/api/workspace?view=pipeline'
        raw = json.dumps(body).encode()
        handler.headers = {'Content-Length': str(len(raw))}
        handler.rfile = io.BytesIO(raw)
        captured = {}
        with patch.object(workspace_api, 'require_auth', return_value=user), \
                patch.object(workspace_api, 'supabase_enabled', return_value=True), \
                patch.object(workspace_api, 'change_opportunity_stage', side_effect=error, return_value={'opportunity': {'id': 1}}) as save, \
                patch.object(workspace_api, 'send_json', side_effect=lambda h,s,p,**k: captured.update(status=s,payload=p)):
            handler.do_POST()
            captured['calls'] = save.call_args_list
        return captured

    def test_command_uses_session_actor_and_role(self):
        result = self.post(self.body(actor='hacker@example.com', is_admin=True))
        self.assertEqual(result['status'], 200)
        call = result['calls'][0].kwargs
        self.assertEqual(call['actor'], 'sales@example.com')
        self.assertIs(call['is_admin'], False)
        self.assertEqual(call['expected_opportunity'], 0)
        self.assertEqual(len(call['hash']), 64)

    def test_malformed_values_return_400_without_database_mutation(self):
        invalid = [dict(stage={}), dict(note=[]), dict(service_slug=[]), dict(amount=True),
                   dict(amount='NaN', amount_unknown=False), dict(amount='1.234',amount_unknown=False),
                   dict(amount='2',amount_unknown=True), dict(amount_unknown='true'),
                   dict(lead_id=True), dict(expected_lead_revision='0'), dict(expected_opportunity_revision=None),
                   dict(idempotency_key='x'), dict(stage='lost', note='  ')]
        for values in invalid:
            with self.subTest(values=values):
                result = self.post(self.body(**values))
                self.assertEqual(result['status'], 400)
                self.assertEqual(result['calls'], [])

    def test_amount_normalization_and_request_hash(self):
        first = command(self.body(stage='won', amount=12000.50, amount_unknown=False))
        same = command(self.body(stage='won', amount='12000.50', amount_unknown=False))
        changed = command(self.body(stage='won', amount='13000.00', amount_unknown=False))
        self.assertEqual(first['amount'], '12000.50')
        self.assertEqual(first['hash'], same['hash'])
        self.assertNotEqual(first['hash'], changed['hash'])

    def test_database_conflict_keeps_code_and_status(self):
        result = self.post(self.body(), error=supabase.CommandRejected(409,'OPPORTUNITY_VERSION_CONFLICT'))
        self.assertEqual(result['status'], 409)
        self.assertEqual(result['payload']['code'], 'OPPORTUNITY_VERSION_CONFLICT')

    def test_history_cursor_and_session_scope(self):
        handler = workspace_api.handler.__new__(workspace_api.handler)
        handler.path, handler.headers = '/api/workspace?view=pipeline&lead_id=101&before=20', {}
        captured = {}
        with patch.object(workspace_api, 'require_auth', return_value=USER), \
                patch.object(workspace_api, 'supabase_enabled', return_value=True), \
                patch.object(workspace_api, 'fetch_opportunity_history', return_value=[{'id': 19}]) as history, \
                patch.object(workspace_api, 'send_json', side_effect=lambda h,s,p,**k: captured.update(status=s,payload=p)):
            handler.do_GET()
        self.assertEqual(captured['status'], 200)
        self.assertEqual(history.call_args.kwargs, {'actor':'sales@example.com','is_admin':False,'lead_id':101,'before':20})
        self.assertIsNone(captured['payload']['next_before'])

    def test_readiness_keeps_worker_checks_and_adds_opportunity_checks(self):
        with patch.object(supabase, 'fetch_schema_readiness', return_value={'version': '013', 'checks': {'worker_heartbeat': False}}), \
                patch.object(supabase, '_rpc', return_value={'opportunity_command': True}):
            result = supabase.schema_status()
        self.assertFalse(result['ready'])
        self.assertEqual(result['failed_checks'], ['worker_heartbeat'])

    def test_pipeline_win_counts_once_without_inventing_a_contact(self):
        now = datetime(2026,10,10,10,tzinfo=timezone.utc)
        leads = [{'lead_id':101,'name':'Demo','status':'converted','scoring':{'score':50,'grade':'C'}}]
        events = [
            {'lead_name':'Demo','action':'opportunity_stage_changed','outcome':'won','happened_at':now.isoformat()},
            {'lead_name':'Demo','action':'opportunity_stage_changed','outcome':'won','happened_at':now.isoformat()},
        ]
        result = build_metrics(leads,events,{},period='30',now=now)
        self.assertEqual(result['sales']['won_businesses']['value'],1)
        self.assertEqual(result['sales']['contact_results']['value'],0)
        self.assertEqual(result['sales']['contacted_businesses']['value'],0)
        events.append({'lead_name':'Demo','action':'contact_result_recorded','outcome':'won','happened_at':now.isoformat()})
        result = build_metrics(leads,events,{},period='30',now=now)
        self.assertEqual(result['sales']['won_businesses']['value'],1)
        self.assertEqual(result['sales']['contact_results']['value'],1)


if __name__ == '__main__': unittest.main()
