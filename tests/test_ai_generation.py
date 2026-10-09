"""WP08: generation fingerprint, one paid call per input, per-call usage ledger."""

import io
import json
import os
import tempfile
import threading
import time
from pathlib import Path
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import httpx

import api.admin_search as admin_search_api
import api.lead_ai as lead_ai_api
from src.ai import cache, generator, llm, pricing, usage
from src.ai.llm import LLMResult

LEAD = {
    "lead_id": 7, "name": "Örnek Klinik", "sector": "health", "city": "Istanbul Kadikoy", "phone": "0216 000 00 00",
    "website": {"website_url": "http://old-site.example/"}, "matched_services": [{"name": "Website", "slug": "website_creation"}],
    "research": {"google_places": {"status": "verified", "rating": 4.5, "refreshed_at": "2026-09-01T00:00:00+00:00"}},
}


class FakeRemote:
    """In-memory stand-in for ai_generations + the 011 RPCs (SQL tested in tests/sql/)."""

    def __init__(self):
        self.rows = {}
        self.ledger = []
        self.lock = threading.Lock()
        self.today_cost = 0.0

    def is_enabled(self):
        return True

    def claim_ai_generation(self, *, cache_key, owner, lease_seconds, **meta):
        with self.lock:
            row = self.rows.get(cache_key)
            if row is None:
                self.rows[cache_key] = {"status": "pending", "owner": owner, "until": time.monotonic() + lease_seconds, **meta}
                return {"status": "claimed"}
            if row["status"] == "ready":
                return {"status": "ready", "content": row["content"], "provider": row["provider"], "model": row["model"]}
            if row["status"] == "pending" and row["until"] > time.monotonic() and row["owner"] != owner:
                return {"status": "busy"}
            row.update(status="pending", owner=owner, until=time.monotonic() + lease_seconds)
            return {"status": "claimed"}

    def complete_ai_generation(self, *, cache_key, content, provider, model, usage):
        with self.lock:
            row = self.rows[cache_key]
            if row["status"] == "ready":
                return False
            row.update(status="ready", content=content, provider=provider, model=model)
            return True

    def replace_ai_generation(self, *, cache_key, content, provider, model, usage):
        self.rows[cache_key].update(status="ready", content=content, provider=provider, model=model)

    def fail_ai_generation(self, *, cache_key, owner, error):
        row = self.rows[cache_key]
        if row["owner"] == owner and row["status"] == "pending":
            row.update(status="failed", error=error)

    def insert_usage_event(self, row):
        self.ledger.append(row)

    def fetch_model_rates(self):
        return []

    def fetch_spend_summary(self, *, today_start=None):
        return {"today_cost_usd": self.today_cost}

    def patches(self):
        names = ("is_enabled", "claim_ai_generation", "complete_ai_generation", "replace_ai_generation",
                 "fail_ai_generation", "insert_usage_event", "fetch_model_rates", "fetch_spend_summary")
        return [patch(f"src.storage.supabase.{name}", getattr(self, name)) for name in names]


class Provider:
    """complete_chat stand-in: counts calls and reports one successful attempt."""

    def __init__(self, delay=0.0):
        self.calls = 0
        self.delay = delay

    def __call__(self, system, prompt, *, on_attempt=None, model=None, **_):
        self.calls += 1
        time.sleep(self.delay)
        used = {"prompt_tokens": 1000, "prompt_cache_hit_tokens": 200, "completion_tokens": 100, "total_tokens": 1100}
        if on_attempt:
            on_attempt(provider="deepseek", model=model or "deepseek-v4-flash", outcome="success", usage=used, error=None)
        return LLMResult(content=f"rapor {self.calls}", provider="deepseek", model=model or "deepseek-v4-flash", usage=used)


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.remote = FakeRemote()
        self.provider = Provider()
        self.stack = ExitStack()
        for item in self.remote.patches():
            self.stack.enter_context(item)
        self.stack.enter_context(patch.object(generator, "complete_chat", self.provider))
        self.stack.enter_context(patch.object(generator, "active_provider", return_value="deepseek"))
        self.stack.enter_context(patch.dict(os.environ, {"AI_LOCAL_CACHE": "0", "DEEPSEEK_API_KEY": "x"}))
        pricing._rate_rows = None
        self.addCleanup(self.stack.close)

    def report(self, lead=LEAD):
        return generator.generate_report(dict(lead))

    def test_same_input_is_paid_once(self):
        with usage.usage_context(job_id=11) as counters:
            first, second = self.report(), self.report()
        self.assertEqual(first, second)
        self.assertEqual(self.provider.calls, 1)
        self.assertEqual(counters, {"provider_calls": 1, "cache_hits": 1, "cost_usd": counters["cost_usd"]})
        outcomes = [row["outcome"] for row in self.remote.ledger]
        self.assertEqual(outcomes, ["success", "cache_hit"])
        self.assertTrue(all(row["job_id"] == 11 for row in self.remote.ledger))

    def test_any_change_to_what_the_model_sees_is_new_work(self):
        self.report()
        self.report({**LEAD, "website": {"website_url": "https://new-site.example"}})
        self.assertEqual(self.provider.calls, 2)

    def test_places_bookkeeping_alone_is_not_new_input(self):
        self.report()
        touched = json.loads(json.dumps(LEAD))
        touched["research"]["google_places"].update(
            refreshed_at="2026-10-08T00:00:00+00:00", last_attempt={"status": "verified", "attempted_at": "2026-10-08T00:00:00+00:00"},
        )
        self.report(touched)
        self.assertEqual(self.provider.calls, 1)
        self.assertEqual(generator.ai_input_fingerprint(LEAD), generator.ai_input_fingerprint(touched))

    def test_catalog_change_is_new_work(self):
        self.report()
        with patch.object(generator, "CATALOG_VERSION", "other-catalog"):
            self.report()
        self.assertEqual(self.provider.calls, 2)

    def test_force_regenerates_and_replaces(self):
        first = self.report()
        forced = generator.generate_report(dict(LEAD), force=True)
        self.assertNotEqual(first, forced)
        self.assertEqual(self.report(), forced)

    def test_concurrent_requests_for_one_input_make_one_paid_call(self):
        self.provider.delay = 0.3
        results = []
        with patch.object(cache, "BUSY_POLL_SECONDS", 0.05):
            threads = [threading.Thread(target=lambda: results.append(self.report())) for _ in range(3)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        self.assertEqual(self.provider.calls, 1)
        self.assertEqual(len(results), 3, "every waiting request gets the text")
        self.assertEqual(len(set(results)), 1)

    def test_a_request_that_waits_too_long_is_told_busy(self):
        self.provider.delay = 0.5
        worker = threading.Thread(target=self.report)
        worker.start()
        time.sleep(0.1)
        with patch.object(cache, "BUSY_WAIT_SECONDS", 0.1), patch.object(cache, "BUSY_POLL_SECONDS", 0.05):
            with self.assertRaises(cache.GenerationBusy):
                self.report()
        worker.join()
        self.assertEqual(self.provider.calls, 1)

    def test_failed_generation_releases_the_key(self):
        def boom(*_a, **_k):
            raise RuntimeError("provider down")

        with patch.object(generator, "complete_chat", boom):
            with self.assertRaises(RuntimeError):
                self.report()
        self.assertEqual(self.report(), "rapor 1")

    def test_local_cache_failure_does_not_block_the_remote_record(self):
        with tempfile.TemporaryDirectory() as folder:
            blocked = os.path.join(folder, "file")
            open(blocked, "w").close()
            with patch.dict(os.environ, {"AI_LOCAL_CACHE": "1", "AI_CACHE_PATH": os.path.join(blocked, "cache.json")}):
                self.assertEqual(self.report(), "rapor 1")
        self.assertTrue(any(row["status"] == "ready" for row in self.remote.rows.values()))

    def test_budget_cap_stops_paid_calls_but_not_cache_hits(self):
        self.report()
        self.remote.today_cost = 5.0
        with patch.dict(os.environ, {"AI_DAILY_BUDGET_USD": "5"}):
            self.assertEqual(self.report(), "rapor 1")  # cache hit, free
            with self.assertRaises(usage.BudgetExceeded):
                self.report({**LEAD, "phone": "0216 111 11 11"})
        self.assertEqual(self.provider.calls, 1)

    def test_report_state_follows_the_data(self):
        enriched = generator.enrich_ai_fields(dict(LEAD))
        self.assertEqual(generator.ai_state(enriched), "current")
        self.assertEqual(generator.ai_state({**enriched, "phone": "0216 999 99 99"}), "stale")
        self.assertEqual(generator.ai_state({**enriched, "ai_input_hash": None}), "unknown")
        self.assertEqual(generator.ai_state(LEAD), "none")


class ProviderAttemptTests(unittest.TestCase):
    """Real llm._deepseek_chat against a fake DeepSeek: every request is reported."""

    def setUp(self):
        self.remote = FakeRemote()
        self.stack = ExitStack()
        for item in self.remote.patches():
            self.stack.enter_context(item)
        self.stack.enter_context(patch.dict(os.environ, {"DEEPSEEK_API_KEY": "x", "AI_PROVIDER": "deepseek"}))
        pricing._rate_rows = None
        self.addCleanup(self.stack.close)

    def _run(self, responses):
        replies = iter(responses)
        real_client = httpx.Client

        def handler(request):
            status, body = next(replies)
            return httpx.Response(status, json=body)

        def on_attempt(**attempt):
            usage.record(task="report", requested_model="deepseek-v4-pro", **attempt)

        with patch.object(llm.httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler))):
            return llm.complete_chat("s", "p", model="deepseek-v4-pro", on_attempt=on_attempt)

    @staticmethod
    def _reply(content, tokens):
        return 200, {"choices": [{"message": {"content": content}}],
                     "usage": {"prompt_tokens": tokens, "prompt_cache_hit_tokens": 0, "completion_tokens": 10}}

    def test_empty_answer_and_fallback_are_both_recorded(self):
        result = self._run([self._reply("", 900), self._reply("tamam", 800)])
        self.assertEqual(result.model, "deepseek-v4-flash")
        rows = self.remote.ledger
        self.assertEqual([(row["model"], row["outcome"]) for row in rows],
                         [("deepseek-v4-pro", "empty"), ("deepseek-v4-flash", "success")])
        self.assertEqual(rows[0]["prompt_tokens"], 900)
        self.assertIsNotNone(rows[0]["actual_cost_usd"])
        self.assertEqual(rows[1]["rates"]["source"], "settings")

    def test_failed_request_is_recorded_before_the_fallback(self):
        result = self._run([(500, {"error": "boom"}), self._reply("tamam", 800)])
        self.assertEqual(result.content, "tamam")
        self.assertEqual([row["outcome"] for row in self.remote.ledger], ["error", "success"])
        self.assertIn("HTTPStatusError", self.remote.ledger[0]["meta"]["error"])


class PricingTests(unittest.TestCase):
    def setUp(self):
        pricing._rate_rows = None
        self.addCleanup(setattr, pricing, "_rate_rows", None)

    def test_usage_split_reads_each_provider_shape(self):
        self.assertEqual(pricing.usage_split({"prompt_tokens": 100, "prompt_cache_hit_tokens": 40, "completion_tokens": 5})["cached_tokens"], 40)
        self.assertEqual(pricing.usage_split({"prompt_tokens": 100, "prompt_tokens_details": {"cached_tokens": 30}})["cached_tokens"], 30)
        self.assertEqual(pricing.usage_split({"prompt_tokens": 10, "cached_tokens": 50})["cached_tokens"], 10)

    def test_rate_table_beats_settings_and_respects_start_dates(self):
        rows = [
            {"provider": "deepseek", "model": "m", "effective_from": "2026-01-01", "input_usd_per_m": 1, "cached_input_usd_per_m": 0.1, "output_usd_per_m": 2},
            {"provider": "deepseek", "model": "m", "effective_from": "2026-09-01", "input_usd_per_m": 3, "cached_input_usd_per_m": 0.3, "output_usd_per_m": 4},
            {"provider": "deepseek", "model": "m", "effective_from": "2099-01-01", "input_usd_per_m": 9, "cached_input_usd_per_m": 9, "output_usd_per_m": 9},
        ]
        with patch("src.storage.supabase.is_enabled", return_value=True), patch("src.storage.supabase.fetch_model_rates", return_value=rows):
            rates = pricing.rates_for("deepseek", "m")
        self.assertEqual((rates["input"], rates["source"], rates["effective_from"]), (3.0, "ai_model_rates", "2026-09-01"))
        split = {"prompt_tokens": 1_000_000, "cached_tokens": 500_000, "completion_tokens": 1_000_000, "total_tokens": 2_000_000}
        self.assertEqual(pricing.cost_usd(split, rates), round(1.5 + 0.15 + 4, 6))

    def test_unknown_provider_is_unpriced_not_guessed(self):
        with patch("src.storage.supabase.is_enabled", return_value=False):
            self.assertIsNone(pricing.rates_for("groq", "llama"))
            row = usage.record(task="report", provider="groq", requested_model="llama", model="llama", outcome="success",
                               usage={"prompt_tokens": 10, "completion_tokens": 5})
        self.assertIsNone(row["actual_cost_usd"])


class AdminEstimateTests(unittest.TestCase):
    def _get(self, path):
        handler = admin_search_api.handler.__new__(admin_search_api.handler)
        handler.path, handler.headers = path, {}
        captured = {}
        with patch.object(admin_search_api, "require_admin", return_value={"sub": "a"}), \
                patch.object(admin_search_api, "supabase_enabled", return_value=True), \
                patch("src.storage.supabase.is_enabled", return_value=False), \
                patch.object(admin_search_api, "send_json", lambda _h, status, payload, **_: captured.update(status=status, payload=payload)):
            handler.do_GET()
        return captured

    def test_panel_estimate_is_the_reserved_estimate(self):
        shown = self._get("/api/admin_search?estimate=1&max_results=12&deep_research=0&ai_mode=pro")["payload"]["estimate"]
        with patch("src.storage.supabase.is_enabled", return_value=False):
            reserved = admin_search_api.estimate_search_tokens(max_results=12, deep_research=False, ai_mode="pro")
        self.assertEqual(shown, reserved)
        self.assertEqual(shown["estimated_tokens"], 12 * 5200)
        self.assertTrue(shown["priced"])

    def test_invalid_mode_is_rejected(self):
        self.assertEqual(self._get("/api/admin_search?estimate=1&ai_mode=turbo")["status"], 400)

    def test_frontend_no_longer_prices_tokens_itself(self):
        template = Path("src/dashboard/template.html").read_text(encoding="utf-8")
        self.assertNotIn("/ 1000000 *", template)
        self.assertIn("/api/admin_search?${params}", template)


class LeadAiEndpointTests(unittest.TestCase):
    def _post(self, enrich, stored_extra=None):
        stored = {**LEAD, **(stored_extra or {})}
        upserts, captured = [], {}
        handler = lead_ai_api.handler.__new__(lead_ai_api.handler)
        raw = json.dumps({"name": LEAD["name"]}).encode()
        handler.path, handler.headers, handler.rfile = "/api/lead_ai", {"Content-Length": str(len(raw))}, io.BytesIO(raw)
        handler.log_error = lambda *a: None
        with patch.object(lead_ai_api, "require_auth", return_value={"sub": "ali@example.com", "role": "admin"}), \
                patch.object(lead_ai_api, "supabase_enabled", return_value=True), \
                patch.object(lead_ai_api, "require_lead_access", lambda *_: None), \
                patch.object(lead_ai_api, "fetch_lead_by_name", lambda _n: dict(stored)), \
                patch.object(lead_ai_api, "fetch_activity_states", lambda _ids: {}), \
                patch.object(lead_ai_api, "enrich_ai_fields", enrich), \
                patch.object(lead_ai_api, "upsert_leads", upserts.extend), \
                patch.object(lead_ai_api, "insert_audit_event", lambda **_: None), \
                patch.object(lead_ai_api, "send_json", lambda _h, status, payload, **_: captured.update(status=status, payload=payload)):
            handler.do_POST()
        return captured, upserts

    def test_unchanged_input_is_served_from_cache_without_writing(self):
        def all_hits(lead):
            usage.record(task="report", provider="deepseek", requested_model="m", model="m", outcome="cache_hit")
            return {**lead, "ai_report": "rapor", "ai_input_hash": "same"}

        with patch("src.storage.supabase.is_enabled", return_value=False):
            captured, upserts = self._post(all_hits, {"ai_input_hash": "same", "ai_report": "rapor"})
        self.assertEqual(captured["status"], 200)
        self.assertTrue(captured["payload"]["cached"])
        self.assertEqual(upserts, [])

    def test_busy_and_budget_have_their_own_answers(self):
        def busy(_lead):
            raise cache.GenerationBusy("report")

        def broke(_lead):
            raise usage.BudgetExceeded("cap")

        self.assertEqual(self._post(busy)[0]["status"], 409)
        self.assertEqual(self._post(broke)[0]["status"], 429)


class WorkerTests(unittest.TestCase):
    def _process(self, scan):
        import asyncio
        import scripts.process_search_jobs as worker

        released, updates = [], []
        with patch.object(worker, "run_scan", scan), \
                patch.object(worker, "update_search_job", lambda job_id, **kw: updates.append(kw)), \
                patch.object(worker, "record_reservation_release", lambda job_id, status: released.append((job_id, status))):
            try:
                asyncio.run(worker.process_job({"id": 5, "query": "q", "city": "c", "max_results": 1, "created_by": "a@x"}))
            except RuntimeError:
                pass
        return released, updates

    def test_usage_rows_carry_the_job_and_the_reservation_is_released(self):
        seen = []

        async def scan(**_):
            seen.append(usage.current())
            return {"leads": 1}

        released, updates = self._process(scan)
        self.assertEqual(seen[0]["job_id"], 5)
        self.assertEqual(released, [(5, "success")])
        self.assertEqual(updates[-1]["status"], "success")

    def test_failed_job_still_releases_its_reservation(self):
        async def scan(**_):
            raise RuntimeError("scrape failed")

        released, updates = self._process(scan)
        self.assertEqual(released, [(5, "failed")])
        self.assertEqual(updates[-1]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
