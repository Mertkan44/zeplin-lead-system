"""Durable search orchestration. No local lead exports or disk checkpoints.

Every completed stage is saved remotely. The frozen research snapshot makes
retries use the same AI key; successful texts survive even a crash before the
stage checkpoint. Job and generation attempts are bounded in the database.
"""
from __future__ import annotations

import asyncio
import hashlib
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone

from playwright.async_api import async_playwright

from besiktas import audit_one, scrape
from scripts.migrate_leads import normalize_lead
from src.ai.generator import (AI_PROMPT_VERSION, ai_input_fingerprint, generate_email,
                              generate_report, generate_research_brief, has_email_evidence)
from src.ai.usage import usage_context
from src.activity import manual_verification_from_event
from src.lead_facts import apply_effective_facts
from src.research import enrich_research
from src.storage import supabase as db

STAGES = ['listed', 'audited', 'researched', 'brief', 'report', 'email', 'synced']


class LeaseLost(RuntimeError):
    pass


def safe_error(stage: str, exc: Exception) -> dict:
    # Provider exceptions can contain URLs, authorization and request content.
    # Expose only a bounded class/code; never those raw exception strings.
    return {'stage': stage, 'code': type(exc).__name__,
            'message': 'Bu aşama tamamlanamadı. Deneme sınırı içinde yeniden denenecek.'}


def listing_key(lead: dict) -> str:
    value = f"{lead.get('maps_url', '')}|{lead['name']}|{lead.get('city', '')}"
    return hashlib.sha256(value.encode()).hexdigest()


def freeze_generation_input(lead: dict, deep_research: bool) -> dict:
    # Reuse the same effective-facts policy as /api/lead_ai. Keep that snapshot
    # only in the private checkpoint; don't write manual overlays into scrape raw.
    stored = db.fetch_lead_by_id(lead['lead_id'])
    if not stored:
        raise RuntimeError('persisted lead not readable')
    source = {**stored, **lead}
    source['research'] = {**(stored.get('research') or {}), **(lead.get('research') or {})}
    state = db.fetch_activity_states([lead['lead_id']]).get(lead['lead_id']) or {}
    effective = apply_effective_facts({**source, 'manual_verification':
        manual_verification_from_event(state.get('latest_manual_verification'))})
    if deep_research:
        researched = enrich_research(effective)
        source['research'] = {**source['research'], **(researched.get('research') or {})}
        effective['research'] = source['research']
    source['_generation_input'] = effective
    return source


@asynccontextmanager
async def audit_session():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        try:
            context = await browser.new_context(locale='tr-TR', viewport={'width': 1280, 'height': 800})
            yield await context.new_page()
        finally:
            await browser.close()


class SearchWorker:
    def __init__(self, job: dict):
        self.job = job
        self.id = int(job['id'])
        self.owner = job['lease_owner']
        self.stage = 'starting'
        self.lost = False
        self.checkpoints = {}

    async def guard(self):
        if self.lost or not await asyncio.to_thread(db.heartbeat_search_job, self.id, self.owner):
            self.lost = True
            raise LeaseLost('search lease lost')

    async def begin_stage(self, stage):
        await self.guard()
        self.stage = stage
        if not await asyncio.to_thread(db.set_search_job_stage, self.id, self.owner, stage):
            raise LeaseLost('search lease lost')

    async def heartbeat(self):
        while True:
            await asyncio.sleep(30)
            try:
                await self.guard()
            except Exception:
                self.lost = True
                return

    async def save(self, key, stage, payload, *, error=None, persist=False):
        await self.guard()
        if persist:
            lead_id = await asyncio.to_thread(db.persist_search_lead, self.id, self.owner, key, stage, payload, error=error)
            if not lead_id:
                raise LeaseLost('search lease lost')
            payload['lead_id'] = lead_id
        else:
            ok = await asyncio.to_thread(db.checkpoint_search_job, self.id, self.owner, key, stage, payload,
                                         lead_id=payload.get('lead_id'), error=error)
            if not ok:
                raise LeaseLost('search lease lost')
        self.checkpoints[key] = {'stage': stage, 'payload': dict(payload), 'error': error}

    async def scan(self):
        self.checkpoints = await asyncio.to_thread(db.fetch_search_checkpoints, self.id)
        await self.guard()
        discovery = self.checkpoints.get('_discovery')
        if discovery is None:
            await self.begin_stage('scrape')
            raw = await scrape(self.job['query'], self.job['city'], int(self.job['max_results']), verbose=False)
            # Deduplicate exact listings, preserving order and the frozen result set.
            raw = list({listing_key(lead): lead for lead in raw}.values())
            if not raw:
                raise RuntimeError('no listings; scraping may have failed')
            await self.save('_discovery', 'scraped', {'items': raw})
        else:
            raw = discovery['payload']['items']

        failures = []
        async with audit_session() as page:
            for listing in raw:
                key = listing_key(listing)
                saved = self.checkpoints.get(key) or {'stage': 'listed', 'payload': listing}
                lead, stage = dict(saved['payload']), saved['stage']
                if stage == 'synced':
                    continue
                try:
                    await self.guard()
                    if STAGES.index(stage) < STAGES.index('audited'):
                        await self.begin_stage('audit')
                        lead = await audit_one(page, lead, verbose=False)
                        await self.save(key, 'audited', lead, persist=True)
                        stage = 'audited'
                    if STAGES.index(stage) < STAGES.index('researched'):
                        await self.begin_stage('research')
                        lead['_ai_mode'] = self.job.get('ai_mode') or 'smart'
                        lead = await asyncio.to_thread(freeze_generation_input, lead, bool(self.job.get('deep_research')))
                        await self.save(key, 'researched', lead)
                        stage = 'researched'
                    with usage_context(lead_id=lead['lead_id']):
                        for next_stage, field, generate in [('brief', 'research_brief', generate_research_brief),
                                                            ('report', 'ai_report', generate_report),
                                                            ('email', 'ai_email', generate_email)]:
                            if STAGES.index(stage) >= STAGES.index(next_stage):
                                continue
                            await self.begin_stage(next_stage)
                            generation_input = lead['_generation_input']
                            if next_stage == 'email' and not has_email_evidence(generation_input):
                                lead[field] = None
                            else:
                                text = await asyncio.to_thread(generate, generation_input, force=False)
                                lead[field] = None if next_stage == 'email' and text.strip().upper().startswith('TASLAK İÇİN YETERLİ KANIT YOK') else text
                            await self.save(key, next_stage, lead)
                            stage = next_stage
                    await self.begin_stage('sync')
                    lead['ai_input_hash'] = ai_input_fingerprint(lead['_generation_input'])
                    lead['ai_prompt_version'] = AI_PROMPT_VERSION
                    lead['ai_generated_at'] = datetime.now(timezone.utc).isoformat()
                    lead['last_analyzed'] = datetime.now(timezone.utc).isoformat()
                    lead.pop('_ai_mode', None)
                    lead = normalize_lead(lead)
                    await self.save(key, 'synced', lead, persist=True)
                except LeaseLost:
                    raise
                except Exception as exc:
                    error = safe_error(self.stage, exc)
                    failures.append({'item_key': key, **error})
                    # Keep the last successful stage so retry only redoes the failed
                    # operation. Partial audited data is already visible as a lead.
                    await self.save(key, stage, lead, error=error)
        return {'requested': self.job['max_results'], 'found': len(raw),
                'completed': sum(row['stage'] == 'synced' for row in self.checkpoints.values()),
                'failures': failures}

    async def process(self):
        heartbeat = asyncio.create_task(self.heartbeat())
        try:
            with usage_context(job_id=self.id, job_owner=self.owner, actor_email=self.job.get('created_by')) as counters:
                try:
                    result = await self.scan()
                    error = result['failures'][0] if result['failures'] else None
                except LeaseLost:
                    return 'lease_lost'
                except Exception as exc:
                    error = safe_error(self.stage, exc)
                    result = {'failures': [error]}
                result['ai_usage'] = dict(counters)
                await self.guard()
                return await asyncio.to_thread(db.finish_search_job, self.id, self.owner, result, error)
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat


async def process_job(job: dict) -> str:
    return await SearchWorker(job).process()
