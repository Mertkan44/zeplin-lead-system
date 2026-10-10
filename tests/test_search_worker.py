"""WP12: kill/resume, partial failure, fencing and paid-call linkage; no providers."""
import asyncio
import copy
import io
import json
import os
import unittest
from contextlib import ExitStack, asynccontextmanager
from unittest.mock import patch

from src import search_worker as worker
from src.ai import cache, usage
from src.ai.llm import LLMResult
import api.admin_search as api

LISTING = {'name': 'Sentetik Kafe', 'city': 'Istanbul', 'query': 'kafe', 'maps_url': 'https://maps.example/demo'}
JOB = {'id': 12, 'lease_owner': 'owner-a', 'attempt_count': 1, 'max_attempts': 3,
       'query': 'kafe', 'city': 'Istanbul', 'max_results': 1, 'deep_research': True,
       'ai_mode': 'flash', 'created_by': 'admin@example.com'}


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.state, self.generations, self.paid, self.ledger = {}, {}, [], []
        self.finished, self.operations = [], []
        self.held, self.crash_at, self.fail_report = True, None, False
        self.stack.enter_context(patch.dict(os.environ, {'AI_LOCAL_CACHE': '0'}))

        @asynccontextmanager
        async def session():
            yield object()

        async def scrape(*args, **kwargs):
            self.operations.append('scrape')
            return [dict(LISTING)]

        async def audit(page, lead, **kwargs):
            self.operations.append('audit')
            return {**lead, 'sector': 'cafe', 'audit_findings': [{'status': 'confirmed', 'confidence': 90, 'service_slugs': ['website_creation']}]}

        def research(lead):
            self.operations.append('research')
            return dict(lead)

        def save(job_id, owner, key, stage, payload, **kwargs):
            if stage == self.crash_at:
                self.crash_at = None
                raise asyncio.CancelledError()  # process dies after a paid answer, before its checkpoint
            if not self.held:
                return False
            self.state[key] = copy.deepcopy({'stage': stage, 'payload': payload, 'error': kwargs.get('error')})
            return True

        def persist(job_id, owner, key, stage, payload, **kwargs):
            if not self.held:
                return None
            save(job_id, owner, key, stage, {**payload, 'lead_id': 42}, **kwargs)
            return 42

        def finish(job_id, owner, result, error):
            self.finished.append((copy.deepcopy(result), error))
            return 'retry_wait' if error else 'success'

        def claim(**kwargs):
            key = kwargs['cache_key']
            if self.generations.get(key, {}).get('status') == 'ready':
                return self.generations[key]
            self.generations[key] = {'status': 'pending', 'owner': kwargs['owner']}
            return {'status': 'claimed'}

        def complete(**kwargs):
            self.generations[kwargs['cache_key']] = {'status': 'ready', **kwargs}
            return True

        def generate(task):
            def run(lead, **kwargs):
                def call():
                    self.paid.append(task)
                    usage.record(task=task, provider='unpriced', requested_model='fixture', model='fixture',
                                 outcome='success', usage={'prompt_tokens': 5, 'completion_tokens': 2}, cache_key=task)
                    if task == 'report' and self.fail_report:
                        raise ValueError('private provider request must never reach the panel')
                    return LLMResult(task+' result', 'unpriced', 'fixture', {})
                return cache.get_or_generate(key=task, task=task, provider='unpriced', requested_model='fixture',
                    meta={'lead_id': lead['lead_id']}, generate=call)
            return run

        patches = [
            patch.object(worker, 'audit_session', session), patch.object(worker, 'scrape', scrape),
            patch.object(worker, 'audit_one', audit), patch.object(worker, 'enrich_research', research),
            patch.object(worker.db, 'heartbeat_search_job', lambda *_: self.held),
            patch.object(worker.db, 'set_search_job_stage', lambda *_: self.held),
            patch.object(worker.db, 'fetch_search_checkpoints', lambda *_: copy.deepcopy(self.state)),
            patch.object(worker.db, 'fetch_lead_by_id', lambda *_: copy.deepcopy(self.state[worker.listing_key(LISTING)]['payload'])),
            patch.object(worker.db, 'fetch_activity_states', lambda *_: {}),
            patch.object(worker.db, 'checkpoint_search_job', save), patch.object(worker.db, 'persist_search_lead', persist),
            patch.object(worker.db, 'finish_search_job', finish), patch.object(worker.db, 'is_enabled', lambda: True),
            patch.object(worker.db, 'claim_ai_generation', claim), patch.object(worker.db, 'complete_ai_generation', complete),
            patch.object(worker.db, 'fail_ai_generation', lambda **_: None),
            patch.object(worker.db, 'insert_usage_event', self.ledger.append),
            patch.object(worker, 'generate_research_brief', generate('brief')),
            patch.object(worker, 'generate_report', generate('report')), patch.object(worker, 'generate_email', generate('email')),
        ]
        for item in patches:
            self.stack.enter_context(item)

    async def test_fresh_worker_needs_no_local_export_and_usage_links_job_and_lead(self):
        self.assertEqual(await worker.process_job(dict(JOB)), 'success')
        self.assertEqual(self.operations, ['scrape', 'audit', 'research'])
        self.assertEqual(self.paid, ['brief', 'report', 'email'])
        self.assertTrue(all(row['job_id'] == 12 and row['lead_id'] == 42 for row in self.ledger))
        self.assertEqual(self.finished[-1][0]['ai_usage']['provider_calls'], 3)
        self.assertEqual(self.finished[-1][0]['completed'], 1)

    async def test_crash_after_paid_answer_resumes_without_paying_again(self):
        self.crash_at = 'brief'
        with self.assertRaises(asyncio.CancelledError):
            await worker.process_job(dict(JOB))
        self.assertEqual(self.finished, [])  # lease expiry, not fake success
        self.assertEqual(await worker.process_job({**JOB, 'attempt_count': 2}), 'success')
        self.assertEqual(self.operations, ['scrape', 'audit', 'research'])
        self.assertEqual(self.paid.count('brief'), 1)
        self.assertEqual(self.paid.count('report'), 1)
        self.assertEqual(self.paid.count('email'), 1)

    async def test_partial_failure_retries_only_failed_and_remaining_stages(self):
        self.fail_report = True
        self.assertEqual(await worker.process_job(dict(JOB)), 'retry_wait')
        result, error = self.finished[-1]
        self.assertEqual(result['completed'], 0)
        self.assertEqual(error['stage'], 'report')
        self.assertNotIn('private provider', json.dumps(result))
        self.assertEqual(self.state[worker.listing_key(LISTING)]['stage'], 'brief')
        self.fail_report = False
        self.assertEqual(await worker.process_job({**JOB, 'attempt_count': 2}), 'success')
        self.assertEqual(self.operations, ['scrape', 'audit', 'research'])
        self.assertEqual(self.paid, ['brief', 'report', 'report', 'email'])

    async def test_usage_persistence_failure_is_visible_without_repeating_the_call(self):
        with patch.object(worker.db, 'insert_usage_event', side_effect=OSError('storage unavailable')):
            self.assertEqual(await worker.process_job(dict(JOB)), 'success')
        self.assertEqual(self.paid, ['brief', 'report', 'email'])
        self.assertEqual(self.finished[-1][0]['ai_usage']['ledger_errors'], 3)

    async def test_email_without_evidence_is_not_a_paid_call(self):
        with patch.object(worker, 'has_email_evidence', return_value=False):
            self.assertEqual(await worker.process_job(dict(JOB)), 'success')
        self.assertEqual(self.paid, ['brief', 'report'])
        self.assertIsNone(self.state[worker.listing_key(LISTING)]['payload']['ai_email'])

    async def test_completed_job_retry_does_no_external_work(self):
        await worker.process_job(dict(JOB))
        before = (list(self.operations), list(self.paid))
        self.assertEqual(await worker.process_job(dict(JOB)), 'success')
        self.assertEqual((self.operations, self.paid), before)

    async def test_lease_loss_stops_all_work_and_cannot_finish(self):
        self.held = False
        self.assertEqual(await worker.process_job(dict(JOB)), 'lease_lost')
        self.assertEqual(self.operations, [])
        self.assertEqual(self.paid, [])
        self.assertEqual(self.finished, [])

    async def test_heartbeat_runs_while_synchronous_generation_is_blocked(self):
        import threading
        entered, released = threading.Event(), threading.Event()
        calls = []
        def guard(*_):
            calls.append(1)
            return True
        def generate(*_, **__):
            entered.set()
            released.wait(2)
            return 'fixture'
        real_sleep = asyncio.sleep
        async def fast_sleep(_):
            await real_sleep(0.01)
        with patch.object(worker.db, 'heartbeat_search_job', guard), \
             patch.object(worker, 'generate_research_brief', generate), \
             patch.object(worker.asyncio, 'sleep', fast_sleep):
            task = asyncio.create_task(worker.process_job(dict(JOB)))
            await asyncio.to_thread(entered.wait, 2)
            before = len(calls)
            await real_sleep(0.06)
            self.assertGreater(len(calls), before)
            released.set()
            self.assertEqual(await task, 'success')


class AdminControlTests(unittest.TestCase):
    def post(self, payload, admin=True):
        handler = api.handler.__new__(api.handler)
        raw = json.dumps(payload).encode()
        handler.rfile, handler.headers = io.BytesIO(raw), {'Content-Length': str(len(raw))}
        output = {}
        with patch.object(api, 'require_admin', return_value={'sub': 'admin@example.com'}, side_effect=None if admin else PermissionError()), \
             patch.object(api, 'supabase_enabled', return_value=True), \
             patch.object(api, 'control_search_job', return_value={'ok': True}) as control, \
             patch.object(api, 'send_json', lambda _, status, body: output.update(status=status, body=body)):
            handler.do_POST()
            return output, control.call_args_list

    def test_cancel_requires_admin_and_valid_job(self):
        result, calls = self.post({'job_id': 12, 'action': 'cancel'}, admin=False)
        self.assertEqual(result['status'], 401)
        self.assertEqual(calls, [])
        result, calls = self.post({'job_id': 12, 'action': 'cancel'})
        self.assertEqual(result['status'], 200)
        self.assertEqual(calls[0].args, (12, 'cancel'))
        self.assertEqual(self.post({'job_id': -1, 'action': 'retry'})[0]['status'], 400)
        self.assertEqual(self.post({'job_id': 12, 'action': 'erase'})[0]['status'], 400)


class FrozenFactsTests(unittest.TestCase):
    def test_manual_correction_is_used_without_becoming_scrape_raw(self):
        from datetime import datetime, timezone
        from src.activity import encode_manual_note
        lead = {**LISTING, 'lead_id': 42, 'website': {'website_url': 'https://scraped.example'},
                'research': {'google_places': {'status': 'verified', 'place_id': 'test-place'}}}
        event = {'happened_at': datetime.now(timezone.utc).isoformat(), 'actor_email': 'seller@example.com',
                 'note': encode_manual_note({'version': 1, 'kind': 'manual_verification',
                     'website': {'checked': True, 'status': 'working', 'url': 'https://corrected.example'}})}
        with patch.object(worker.db, 'fetch_lead_by_id', return_value=lead), \
             patch.object(worker.db, 'fetch_activity_states', return_value={42: {'latest_manual_verification': event}}), \
             patch.object(worker, 'enrich_research', side_effect=lambda effective: {'research': {'website': {'url': effective['website']['website_url']}}}):
            frozen = worker.freeze_generation_input(dict(lead), True)
        self.assertEqual(frozen['_generation_input']['website']['website_url'], 'https://corrected.example')
        self.assertEqual(frozen['website']['website_url'], 'https://scraped.example')
        self.assertEqual(frozen['research']['google_places']['place_id'], 'test-place')
        self.assertEqual(frozen['research']['website']['url'], 'https://corrected.example')
        self.assertNotIn('_generation_input', worker.db._lead_row(frozen)['raw'])
