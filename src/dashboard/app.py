from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.storage.supabase import (
    fetch_leads_full,
    fetch_outreach_events,
    insert_outreach_event,
    is_enabled as supabase_enabled,
    set_lead_status,
)

PUBLIC_DIR = ROOT / "public"

app = Flask(__name__)
CORS(app)


def _local_leads():
    path = ROOT / "leads_final.json"
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _json_error(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status

@app.route('/api/leads')
def get_leads():
    limit = min(int(request.args.get("limit", 500)), 1000)
    if supabase_enabled():
        try:
            return jsonify(fetch_leads_full(limit=limit))
        except Exception as exc:
            return _json_error(f"supabase leads fetch failed: {exc}", 502)
    return jsonify(_local_leads())


@app.route('/api/status', methods=['POST'])
def update_status():
    payload = request.get_json(silent=True) or {}
    name = payload.get("name")
    status = payload.get("status")
    if not name or not status:
        return _json_error("name and status are required")
    if not supabase_enabled():
        return _json_error("supabase is not configured", 503)
    try:
        set_lead_status(name, status)
        return jsonify({"ok": True})
    except Exception as exc:
        return _json_error(str(exc), 502)


@app.route('/api/outreach', methods=['GET'])
def get_outreach():
    if not supabase_enabled():
        return jsonify([])
    try:
        limit = min(int(request.args.get("limit", 500)), 1000)
        lead_name = request.args.get("lead")
        events = fetch_outreach_events(limit=limit)
        if lead_name:
            events = [event for event in events if event.get("lead_name") == lead_name]
        return jsonify(events)
    except Exception as exc:
        return _json_error(f"supabase outreach fetch failed: {exc}", 502)


@app.route('/api/outreach', methods=['POST'])
def create_outreach():
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
        insert_outreach_event(
            lead_name=lead_name,
            action=action,
            note=note,
            happened_at=happened_at,
        )
        return jsonify({"ok": True})
    except Exception as exc:
        return _json_error(str(exc), 502)

@app.route('/')
def index():
    return send_from_directory(PUBLIC_DIR, 'index.html')

if __name__ == '__main__':
    app.run(port=5050, debug=True)
