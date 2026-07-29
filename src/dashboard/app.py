from flask import Flask, jsonify, request, send_from_directory
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.storage.supabase import (
    fetch_lead_assignments,
    fetch_leads_full,
    fetch_outreach_events,
    insert_outreach_event,
    is_enabled as supabase_enabled,
    set_lead_status,
)
from src.auth import current_user, normalize_email, require_lead_access

PUBLIC_DIR = ROOT / "public"

app = Flask(__name__)


class _RequestAdapter:
    @property
    def headers(self):
        return request.headers


def _user():
    return current_user(_RequestAdapter())


def _json_error(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status

@app.route('/api/leads')
def get_leads():
    user = _user()
    if not user:
        return _json_error("login required", 401)
    limit = min(int(request.args.get("limit", 500)), 1000)
    if supabase_enabled():
        try:
            leads = fetch_leads_full(limit=limit)
            if user.get("role") != "admin":
                assignments = fetch_lead_assignments(
                    user_email=normalize_email(user.get("sub")), status="active", limit=1000
                )
                assigned = {item.get("lead_name") for item in assignments}
                leads = [lead for lead in leads if lead.get("name") in assigned]
            return jsonify(leads)
        except Exception as exc:
            app.logger.exception("Supabase lead fetch failed")
            return _json_error("lead fetch failed", 502)
    return _json_error("supabase is not configured", 503)


@app.route('/api/status', methods=['POST'])
def update_status():
    user = _user()
    if not user:
        return _json_error("login required", 401)
    payload = request.get_json(silent=True) or {}
    name = payload.get("name")
    status = payload.get("status")
    if not name or not status:
        return _json_error("name and status are required")
    if not supabase_enabled():
        return _json_error("supabase is not configured", 503)
    try:
        require_lead_access(user, name)
        set_lead_status(name, status)
        return jsonify({"ok": True})
    except PermissionError as exc:
        return _json_error(str(exc), 403)
    except Exception as exc:
        app.logger.exception("Status save failed")
        return _json_error("status save failed", 502)


@app.route('/api/outreach', methods=['GET'])
def get_outreach():
    user = _user()
    if not user:
        return _json_error("login required", 401)
    if not supabase_enabled():
        return _json_error("supabase is not configured", 503)
    try:
        limit = min(int(request.args.get("limit", 500)), 1000)
        lead_name = request.args.get("lead")
        events = fetch_outreach_events(limit=limit)
        if user.get("role") != "admin":
            assignments = fetch_lead_assignments(
                user_email=normalize_email(user.get("sub")), status="active", limit=1000
            )
            assigned = {item.get("lead_name") for item in assignments}
            events = [event for event in events if event.get("lead_name") in assigned]
        if lead_name:
            events = [event for event in events if event.get("lead_name") == lead_name]
        return jsonify(events)
    except Exception as exc:
        app.logger.exception("Supabase outreach fetch failed")
        return _json_error("outreach fetch failed", 502)


@app.route('/api/outreach', methods=['POST'])
def create_outreach():
    user = _user()
    if not user:
        return _json_error("login required", 401)
    payload = request.get_json(silent=True) or {}
    lead_name = payload.get("lead_name")
    action = payload.get("action")
    note = payload.get("note")
    happened_at = payload.get("happened_at")
    if not lead_name or not action:
        return _json_error("lead_name and action are required")
    if not supabase_enabled():
        return _json_error("supabase is not configured", 503)
    try:
        require_lead_access(user, lead_name)
        insert_outreach_event(
            lead_name=lead_name,
            action=action,
            note=note,
            happened_at=happened_at,
            actor_email=normalize_email(user.get("sub")),
            source="flask",
        )
        return jsonify({"ok": True})
    except PermissionError as exc:
        return _json_error(str(exc), 403)
    except Exception as exc:
        app.logger.exception("Outreach save failed")
        return _json_error("outreach save failed", 502)

@app.route('/')
def index():
    return send_from_directory(PUBLIC_DIR, 'index.html')

if __name__ == '__main__':
    app.run(port=5050, debug=True)
