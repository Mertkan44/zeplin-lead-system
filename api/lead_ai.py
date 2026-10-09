from http.server import BaseHTTPRequestHandler
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ai.cache import GenerationBusy
from src.ai.generator import AI_PROMPT_VERSION, enrich_ai_fields
from src.ai.usage import BudgetExceeded, usage_context
from src.activity import manual_verification_from_event
from src.auth import normalize_email, require_auth, require_lead_access
from src.http_api import read_json, send_internal_error, send_json, send_options
from src.lead_facts import apply_effective_facts
from src.storage.supabase import (
    fetch_activity_states,
    fetch_lead_by_name,
    insert_audit_event,
    is_enabled as supabase_enabled,
    upsert_leads,
)

# What enrich_ai_fields adds; the rest of the effective lead is never stored.
AI_FIELDS = (
    "research_brief", "ai_report", "ai_email", "ai_tier", "ai_prompt_version", "ai_input_hash", "ai_generated_at",
)


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        send_options(self, allow_methods="POST, OPTIONS")

    def do_POST(self):
        try:
            user = require_auth(self)
        except PermissionError:
            send_json(self, 401, {"ok": False, "error": "login required"}, allow_methods="POST, OPTIONS")
            return
        if not supabase_enabled():
            send_json(
                self,
                503,
                {"ok": False, "error": "supabase is not configured"},
                allow_methods="POST, OPTIONS",
            )
            return
        try:
            payload = read_json(self)
        except ValueError as exc:
            send_json(self, 400, {"ok": False, "error": str(exc)}, allow_methods="POST, OPTIONS")
            return

        name = (payload.get("name") or "").strip()
        if not name:
            send_json(self, 400, {"ok": False, "error": "name is required"}, allow_methods="POST, OPTIONS")
            return

        try:
            require_lead_access(user, name)
            stored = fetch_lead_by_name(name)
            if not stored:
                send_json(self, 404, {"ok": False, "error": "lead not found"}, allow_methods="POST, OPTIONS")
                return
            # Generate from the same effective values the team sees (manual
            # corrections included), but store only the AI fields.
            state = fetch_activity_states([stored["lead_id"]]).get(stored["lead_id"]) or {}
            lead = apply_effective_facts(
                {**stored, "manual_verification": manual_verification_from_event(state.get("latest_manual_verification"))}
            )
            if not lead.get("matched_services"):
                send_json(
                    self,
                    409,
                    {"ok": False, "error": "Hizmet eşleşmesi yok; önce ihtiyacı doğrula."},
                    allow_methods="POST, OPTIONS",
                )
                return

            # Every task goes through the generation cache: an unchanged input is
            # a free cache hit, any change to the data the model sees is new work.
            with usage_context(actor_email=normalize_email(user.get("sub")), lead_id=stored.get("lead_id")) as counters:
                enriched = enrich_ai_fields(lead)
            if not enriched.get("ai_report"):
                raise RuntimeError("AI provider returned an empty report")
            cached = counters["provider_calls"] == 0
            if not cached or stored.get("ai_input_hash") != enriched.get("ai_input_hash"):
                upsert_leads([{**stored, **{key: enriched.get(key) for key in AI_FIELDS}}])

            insert_audit_event(
                actor_email=user.get("sub"),
                event_type="lead_ai_generated",
                target_type="lead",
                target_key=name,
                meta={
                    "prompt_version": AI_PROMPT_VERSION,
                    "cached": cached,
                    "provider_calls": counters["provider_calls"],
                    "cache_hits": counters["cache_hits"],
                    "cost_usd": round(counters["cost_usd"], 6),
                },
            )
            send_json(
                self,
                200,
                {
                    "ok": True,
                    "cached": cached,
                    "lead": {
                        "name": name,
                        "ai_prompt_version": enriched.get("ai_prompt_version"),
                        "ai_report": enriched.get("ai_report"),
                        "ai_email": enriched.get("ai_email"),
                        "ai_generated_at": enriched.get("ai_generated_at"),
                        "ai_state": "current",
                    },
                },
                allow_methods="POST, OPTIONS",
            )
        except GenerationBusy:
            send_json(
                self,
                409,
                {"ok": False, "error": "Bu rapor şu anda başka bir istekte hazırlanıyor; birkaç saniye sonra yenile."},
                allow_methods="POST, OPTIONS",
            )
        except BudgetExceeded as exc:
            self.log_error("AI budget: %s", exc)
            send_json(
                self,
                429,
                {"ok": False, "error": "Günlük AI bütçesi doldu. Yönetici bütçeyi kontrol etmeli."},
                allow_methods="POST, OPTIONS",
            )
        except PermissionError as exc:
            send_json(self, 403, {"ok": False, "error": str(exc)}, allow_methods="POST, OPTIONS")
        except RuntimeError as exc:
            detail = str(exc)
            self.log_error("AI report generation failed: %s", detail)
            if "no available balance" in detail.lower() or "billing is not enabled" in detail.lower():
                message = "DeepSeek bakiyesi yetersiz. Yönetici bakiyeyi kontrol etmeli."
            elif "is missing" in detail.lower():
                message = "AI servisi yapılandırılmamış. Yönetici API ayarlarını kontrol etmeli."
            elif "empty" in detail.lower():
                message = "AI bu işletme için boş yanıt döndürdü. Birkaç saniye sonra tekrar dene."
            else:
                message = "İhtiyaç raporu şu anda üretilemedi. Birkaç saniye sonra tekrar dene."
            send_json(self, 503, {"ok": False, "error": message}, allow_methods="POST, OPTIONS")
        except Exception as exc:
            send_internal_error(self, exc, error="AI report generation failed", allow_methods="POST, OPTIONS")
