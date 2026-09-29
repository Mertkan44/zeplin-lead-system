from http.server import BaseHTTPRequestHandler
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ai.generator import AI_PROMPT_VERSION, ai_input_fingerprint, enrich_ai_fields, has_email_evidence
from src.auth import require_auth, require_lead_access
from src.http_api import read_json, send_internal_error, send_json, send_options, text_field
from src.storage.supabase import (
    fetch_lead_by_name,
    insert_audit_event,
    is_enabled as supabase_enabled,
    patch_lead_fields,
    ConcurrentLeadUpdateError,
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

        try:
            name = text_field(payload, "name", max_len=300)
        except ValueError as exc:
            send_json(self, 400, {"ok": False, "error": str(exc)}, allow_methods="POST, OPTIONS")
            return
        if not name:
            send_json(self, 400, {"ok": False, "error": "name is required"}, allow_methods="POST, OPTIONS")
            return

        try:
            require_lead_access(user, name)
            lead = fetch_lead_by_name(name)
            if not lead:
                send_json(self, 404, {"ok": False, "error": "lead not found"}, allow_methods="POST, OPTIONS")
                return
            if not lead.get("matched_services"):
                send_json(
                    self,
                    409,
                    {"ok": False, "error": "Hizmet eşleşmesi yok; önce ihtiyacı doğrula."},
                    allow_methods="POST, OPTIONS",
                )
                return

            if (
                lead.get("ai_prompt_version") == AI_PROMPT_VERSION
                and lead.get("ai_input_fingerprint") == ai_input_fingerprint(lead)
                and lead.get("ai_report")
                and (lead.get("ai_email") or lead.get("ai_generation_status") == "complete" or not has_email_evidence(lead))
            ):
                enriched = lead
                cached = True
            else:
                enriched = enrich_ai_fields(lead)
                if not enriched.get("ai_report"):
                    raise RuntimeError("AI provider returned an empty report")
                patch_lead_fields(name, lead.get("supabase_updated_at"), {
                    key: enriched.get(key) for key in (
                        "research_brief", "ai_report", "ai_email", "ai_tier", "ai_prompt_version",
                        "ai_input_fingerprint", "ai_generated_at", "ai_generation_status", "last_analyzed"
                    )
                })
                cached = False

            insert_audit_event(
                actor_email=user.get("sub"),
                event_type="lead_ai_generated",
                target_type="lead",
                target_key=name,
                meta={"prompt_version": AI_PROMPT_VERSION, "cached": cached},
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
                    },
                },
                allow_methods="POST, OPTIONS",
            )
        except PermissionError as exc:
            send_json(self, 403, {"ok": False, "error": str(exc)}, allow_methods="POST, OPTIONS")
        except ConcurrentLeadUpdateError as exc:
            send_json(self, 409, {"ok": False, "error": str(exc)}, allow_methods="POST, OPTIONS")
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
