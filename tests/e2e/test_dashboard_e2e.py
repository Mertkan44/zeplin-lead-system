"""End-to-end checks of the built dashboard (public/) in Chromium.

The page is served from public/ with the same fallback and Content-Security-
Policy header Vercel uses (unknown paths get index.html, so a CSP violation
shows up as a console error); the API is mocked in the browser, with the workspace
payload produced by the real api/workspace.py handler from the synthetic
sample leads. Runs only with RUN_E2E=1 (CI's e2e job):

    RUN_E2E=1 python -m unittest discover -s tests/e2e

Set E2E_CHROMIUM_PATH to use an already installed Chromium.
"""

import copy
import json
import os
import threading
import unittest
from contextlib import ExitStack
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "public"
SAMPLE = json.loads((ROOT / "tests" / "fixtures" / "leads_sample.json").read_text(encoding="utf-8"))
CSP = next(
    header["value"]
    for header in json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))["headers"][0]["headers"]
    if header["key"] == "Content-Security-Policy"
)


def workspace_payload(user: dict) -> dict:
    """What /api/workspace returns for `user`, built by the real handler."""
    import api.workspace as workspace

    leads = [{**lead, "lead_id": 100 + index, "status": "yeni"} for index, lead in enumerate(SAMPLE)]
    captured = {}
    names = {lead["name"] for lead in leads}
    with ExitStack() as stack:
        enter = stack.enter_context
        enter(patch.object(workspace, "require_auth", return_value=user))
        enter(patch.object(workspace, "supabase_enabled", return_value=True))
        enter(patch.object(workspace, "lead_read_scope", return_value=None))
        enter(patch.object(workspace, "fetch_all_leads", return_value=leads))
        enter(patch.object(workspace, "fetch_all_assignments", return_value=[]))
        enter(patch.object(workspace, "fetch_activity_states", return_value={}))
        enter(patch.object(workspace, "fetch_events_since", return_value=[]))
        enter(patch.object(workspace, "schema_status", return_value={"ready": True, "version": "011"}))
        enter(patch.object(workspace, "send_json", lambda _h, status, payload, **_: captured.update(payload=payload)))
        handler = workspace.handler.__new__(workspace.handler)
        handler.path, handler.headers = "/api/workspace", {}
        handler.do_GET()
    payload = captured["payload"]
    assert {lead["name"] for lead in payload["leads"]} == names
    return payload


class _SpaHandler(SimpleHTTPRequestHandler):
    """Static files from public/, index.html for any other path (like vercel.json)."""

    def log_message(self, *_args):
        pass

    def end_headers(self):
        self.send_header("Content-Security-Policy", CSP)
        super().end_headers()

    def send_head(self):
        path = self.translate_path(self.path)
        if not os.path.exists(path) or os.path.isdir(path):
            self.path = "/index.html"
        return super().send_head()


@unittest.skipUnless(os.environ.get("RUN_E2E") == "1", "set RUN_E2E=1 to run browser tests")
class DashboardE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_SpaHandler, directory=str(PUBLIC)))
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.playwright = sync_playwright().start()
        executable = os.environ.get("E2E_CHROMIUM_PATH") or None
        cls.browser = cls.playwright.chromium.launch(executable_path=executable)
        cls.admin = {"email": "boss@example.com", "name": "Boss", "role": "admin", "updated_at": "2026-10-10T07:00:00Z"}
        cls.sales = {"email": "seller@example.com", "name": "Satış Kişisi", "role": "sales", "updated_at": "2026-10-10T07:00:00Z"}
        cls.payload = workspace_payload({"sub": cls.admin["email"], **cls.admin})
        # The top lead has passed its checks, so the contact dialog can save.
        top = max(cls.payload["leads"], key=lambda lead: lead["scoring"]["score"])
        top["workflow"] = {**(top.get("workflow") or {}), "ready_to_contact": True, "stage": "ready_to_contact", "stage_label": "Aramaya hazır"}
        cls.payload["integrations"] = {"google_places": True}

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.payload = copy.deepcopy(type(self).payload)
        self.page = self.browser.new_page(viewport={"width": 1280, "height": 900})
        self.errors, self.external = [], []
        self.session = {"user": self.admin}
        self.workspace_status = 200
        self.status_save_status = 200
        self.outreach_statuses = []  # status codes for the next POST /api/outreach calls
        self.outreach_posts = []
        self.place_posts = []
        self.metric_periods = []
        self.team_rows = [{**member, "active": True, "updated_at": "2026-10-10T07:00:00Z", "active_assignments": 3, "overdue_assignments": 1} for member in (self.admin,self.sales)]
        self.team_posts = []
        self.team_statuses = []
        self.password_posts = []
        self.password_status = 200
        self.page.on("pageerror", lambda exc: self.errors.append(str(exc)))
        self.page.on("console", lambda msg: msg.type == "error" and self.errors.append(msg.text))
        self.page.route("**/*", self._route)
        self.addCleanup(self.page.close)

    def _route(self, route):
        request = route.request
        url = request.url
        if not url.startswith(self.base):
            self.external.append(url)
            return route.fulfill(status=204, body="")
        path = url[len(self.base):].split("?")[0]
        if path == "/api/auth":
            if request.method == "POST":
                self.session["user"] = self.admin
                return route.fulfill(json={"ok": True, "user": self.admin})
            if request.method == "DELETE":
                self.session["user"] = None
                return route.fulfill(json={"ok": True})
            user = self.session["user"]
            return route.fulfill(json={"ok": True, "configured": True, "authenticated": bool(user), "user": user})
        if path == "/api/workspace" and "view=metrics" in url:
            from urllib.parse import parse_qs, urlparse

            from src.metrics import build_metrics

            period = parse_qs(urlparse(url).query).get("period", ["30"])[0]
            self.metric_periods.append(period)
            return route.fulfill(json={"ok": True, "metrics": build_metrics(self.payload["leads"], [], {}, period=period)})
        if path == "/api/workspace":
            if self.workspace_status != 200:
                return route.fulfill(status=self.workspace_status, json={"ok": False, "error": "login required"})
            return route.fulfill(json=self.payload)
        if path == "/api/outreach" and request.method == "POST":
            self.outreach_posts.append(json.loads(request.post_data or "{}"))
            status = self.outreach_statuses.pop(0) if self.outreach_statuses else 200
            if status != 200:
                return route.fulfill(status=status, json={"ok": False, "error": "temporary"})
            return route.fulfill(json={"ok": True})
        if path == "/api/place_refresh" and request.method == "POST":
            self.place_posts.append(json.loads(request.post_data or "{}"))
            return route.fulfill(json={"ok": True, "place": {"status": "verified", "match_method": "place_id"}})
        if path == "/api/status" and self.status_save_status != 200:
            return route.fulfill(status=self.status_save_status, json={"ok": False, "error": "status save failed"})
        if path == "/api/users":
            if "view=account" in url and request.method == "PATCH":
                self.password_posts.append(json.loads(request.post_data or "{}"))
                if self.password_status != 200:
                    return route.fulfill(status=self.password_status,json={"ok":False,"error":"Mevcut şifre doğru değil."})
                self.session["user"] = None
                return route.fulfill(json={"ok":True,"session_ended":True})
            if request.method in ("POST","PATCH"):
                body = json.loads(request.post_data or "{}")
                self.team_posts.append(body)
                status = self.team_statuses.pop(0) if self.team_statuses else 200
                if status != 200:
                    if status == 409:
                        current = next(row for row in self.team_rows if row['email']==body['email'])
                        current['updated_at'] = '2026-10-10T07:01:00Z'
                    return route.fulfill(status=status,json={"ok":False,"error":"Kayıt yapılamadı.","code":"USER_VERSION_CONFLICT" if status==409 else None})
                current = next((row for row in self.team_rows if row['email']==body['email']),None)
                if current is None:
                    current = {"email":body['email'],"active_assignments":0,"overdue_assignments":0}
                    self.team_rows.append(current)
                current.update({key:body.get(key) for key in ('name','role','active','title','avatar_url')})
                current['updated_at'] = '2026-10-10T07:02:00Z'
                return route.fulfill(json={"ok":True,"user":current})
            return route.fulfill(json={"ok":True,"users":self.team_rows})
        if path.startswith("/api/"):
            return route.fulfill(json={"ok": True, "users": [], "items": [], "jobs": [], "token_summary": {}})
        return route.continue_()

    def lead(self, index=0):
        return sorted(self.payload["leads"], key=lambda lead: -lead["scoring"]["score"])[index]

    def heading(self, text):
        self.page.get_by_role("heading", name=text).first.wait_for(timeout=15000)

    def test_deep_link_refresh_and_back_keep_the_same_lead(self):
        first, second = self.lead(0), self.lead(1)
        self.page.goto(f"{self.base}/leads/{second['lead_id']}")
        self.heading(second["name"])
        self.page.reload()
        self.heading(second["name"])
        self.page.get_by_role("button", name="Önceki").first.click()
        self.heading(first["name"])
        self.assertEqual(self.page.evaluate("location.pathname"), f"/leads/{first['lead_id']}")
        self.page.get_by_text("Pipeline", exact=True).first.click()
        self.page.wait_for_url(f"{self.base}/pipeline")
        self.page.go_back()
        self.heading(first["name"])
        self.assertEqual(self.errors, [])

    def test_unknown_lead_and_unknown_path(self):
        self.page.goto(f"{self.base}/leads/999999")
        self.heading("Lead bulunamadı")
        self.page.goto(f"{self.base}/nereye")
        self.page.wait_for_url(f"{self.base}/")

    def test_logout_clears_crm_data_and_login_restores_it(self):
        lead = self.lead(0)
        self.page.goto(f"{self.base}/leads/{lead['lead_id']}")
        self.heading(lead["name"])
        self.page.get_by_text("Hesabım", exact=True).first.click()
        self.page.get_by_role("button", name="Çıkış yap").first.click()
        self.page.get_by_role("button", name="Çıkış yap").last.click()  # confirm dialog
        self.page.get_by_placeholder("ad@zeplinmedia.com").wait_for(timeout=10000)
        self.assertEqual(self.page.get_by_text(lead["name"]).count(), 0)
        self.page.get_by_placeholder("ad@zeplinmedia.com").fill(self.admin["email"])
        self.page.get_by_placeholder("••••••••").fill("x")
        self.page.locator("form button:not([type=button])").first.click()
        # Back where the user logged out (the URL survives), with data loaded again.
        self.page.get_by_role("button", name="Çıkış yap").first.wait_for(timeout=15000)
        self.assertEqual(self.page.evaluate("location.pathname"), "/profile")
        self.page.get_by_text("Pipeline", exact=True).first.click()
        self.page.get_by_text(lead["name"]).first.wait_for(timeout=15000)

    def test_expired_session_returns_to_login(self):
        self.workspace_status = 401
        self.page.goto(f"{self.base}/")
        self.page.get_by_text("Oturumun sona erdi").wait_for(timeout=15000)

    def test_every_screen_renders_under_the_production_csp(self):
        lead = self.lead(0)
        screens = {
            "/": "Lead Workspace",
            "/raporlar": "Leadler",
            "/pipeline": "Satış kanalı",
            "/analytics": "Raporlar",
            "/hizmetler": "Zeplin Media Hizmetleri",
            "/profile": "Hesabım ve ayarlar",
            "/admin": "Tarama merkezi",
            "/team": "Ekip yönetimi",
            f"/leads/{lead['lead_id']}": lead["name"],
        }
        for path, title in screens.items():
            with self.subTest(path=path):
                self.page.goto(f"{self.base}{path}")
                self.heading(title)
        self.assertEqual(self.errors, [])

    def test_search_dialog_keeps_focus_inside_and_returns_it(self):
        lead = self.lead(2)
        self.page.goto(f"{self.base}/")
        self.heading("Lead Workspace")
        opener = self.page.get_by_role("button", name="Lead ara")
        opener.click()
        dialog = self.page.get_by_role("dialog", name="Lead ara")
        dialog.wait_for()
        self.assertTrue(self.page.evaluate("document.getElementById('root').inert"))
        for _ in range(6):
            self.page.keyboard.press("Tab")
            self.assertTrue(dialog.evaluate("node => node.contains(document.activeElement)"))
        self.page.keyboard.press("Escape")
        dialog.wait_for(state="detached")
        self.assertTrue(opener.evaluate("node => node === document.activeElement"))

        opener.click()
        self.page.keyboard.type(lead["name"])
        dialog.get_by_role("link", name=lead["name"]).click()
        self.heading(lead["name"])
        self.assertEqual(self.page.evaluate("location.pathname"), f"/leads/{lead['lead_id']}")
        self.assertEqual(self.errors, [])

    def test_failed_status_change_reverts_and_says_so(self):
        lead = self.lead(0)
        self.status_save_status = 500
        self.page.goto(f"{self.base}/leads/{lead['lead_id']}")
        self.heading(lead["name"])
        stage = self.page.get_by_label("Aşama", exact=True)
        stage.select_option("converted")
        self.page.get_by_role("alert").filter(has_text="Durum kaydedilemedi.").wait_for(timeout=10000)
        self.page.wait_for_function("() => document.getElementById('lead-stage').value === 'yeni'")

    def test_only_display_preferences_are_kept_in_browser_storage(self):
        self.page.goto(f"{self.base}/leads/{self.lead(0)['lead_id']}")
        self.heading(self.lead(0)["name"])
        self.page.get_by_role("button", name="Aydınlık moda geç").click()
        self.page.reload()
        self.heading(self.lead(0)["name"])
        self.assertEqual(self.page.evaluate("document.documentElement.dataset.theme"), "light")
        self.assertEqual(set(self.page.evaluate("Object.keys(localStorage)")), {"zeplin_theme", "zeplin_density"})
        self.assertEqual(self.page.evaluate("Object.keys(sessionStorage)"), [])

    def test_contact_result_keeps_the_form_on_failure_and_retries_once(self):
        lead = self.lead(0)
        self.outreach_statuses = [503]
        self.page.goto(f"{self.base}/leads/{lead['lead_id']}")
        self.heading(lead["name"])
        self.page.get_by_role("button", name="Sonuç kaydet", exact=True).click()
        dialog = self.page.get_by_role("dialog", name=lead["name"])
        dialog.wait_for()
        dialog.get_by_role("button", name="Ulaşılamadı", exact=True).click()
        dialog.get_by_label("Görüşme notu").fill("Telefon kapalıydı")
        dialog.get_by_role("button", name="Sonucu kaydet").click()
        dialog.get_by_role("alert").wait_for()
        # Nothing typed or chosen is lost.
        self.assertEqual(dialog.get_by_label("Görüşme notu").input_value(), "Telefon kapalıydı")
        self.assertEqual(dialog.get_by_role("button", name="Ulaşılamadı", exact=True).get_attribute("aria-pressed"), "true")
        dialog.get_by_role("button", name="Sonucu kaydet").click()
        dialog.wait_for(state="detached")
        first, retry = self.outreach_posts
        self.assertEqual(first["idempotency_key"], retry["idempotency_key"])
        self.assertEqual((retry["outcome"], retry["note"], retry["lead_name"]), ("no_answer", "Telefon kapalıydı", lead["name"]))
        # The browser logs the simulated 503 itself; nothing else may fail.
        self.assertEqual([e for e in self.errors if "status of 503" not in e], [])

    def test_closing_a_filled_contact_form_asks_first(self):
        lead = self.lead(0)
        self.page.goto(f"{self.base}/leads/{lead['lead_id']}")
        self.heading(lead["name"])
        self.page.get_by_role("button", name="Sonuç kaydet", exact=True).click()
        dialog = self.page.get_by_role("dialog", name=lead["name"])
        dialog.get_by_role("button", name="İlgilendi", exact=True).click()
        dialog.get_by_text("2 gün sonra 10:00 için takip görevi açılır").wait_for()
        dialog.get_by_role("button", name="Haftaya").click()
        self.page.keyboard.press("Escape")
        confirm = self.page.get_by_role("alertdialog", name="Sonuç kaydedilmedi")
        confirm.wait_for()
        confirm.get_by_role("button", name="Forma dön").click()
        confirm.wait_for(state="detached")
        self.assertEqual(dialog.get_by_role("button", name="İlgilendi", exact=True).get_attribute("aria-pressed"), "true")
        dialog.get_by_role("button", name="Vazgeç").click()
        self.page.get_by_role("alertdialog").get_by_role("button", name="Kaydetmeden kapat").click()
        dialog.wait_for(state="detached")
        self.assertEqual(self.outreach_posts, [])
        self.assertEqual(self.errors, [])

    def test_lead_list_rows_are_links(self):
        lead = self.lead(3)
        self.page.goto(f"{self.base}/raporlar")
        self.heading("Leadler")
        row = self.page.get_by_role("link", name=lead["name"])
        self.assertEqual(row.get_attribute("href"), f"/leads/{lead['lead_id']}")
        row.click()
        self.heading(lead["name"])
        self.page.go_back()
        self.heading("Leadler")

    def test_lead_list_filters_live_in_the_url(self):
        ready = self.lead(0)
        self.page.goto(f"{self.base}/raporlar")
        self.heading("Leadler")
        self.page.get_by_role("button", name="Filtreler").click()
        drawer = self.page.get_by_role("dialog", name="Filtreler")
        drawer.get_by_label("Sonraki iş").select_option("first_contact")
        drawer.get_by_role("button", name="sonucu göster").click()
        self.page.wait_for_url("**/raporlar?is=first_contact")
        rows = self.page.locator("tbody tr")
        self.assertEqual(rows.count(), 1)
        rows.get_by_role("link", name=ready["name"]).wait_for()
        # Back returns to the unfiltered list; forward and the chip's × work too.
        self.page.go_back()
        self.page.wait_for_url(f"{self.base}/raporlar")
        self.assertEqual(rows.count(), len(self.payload["leads"]))
        self.page.go_forward()
        self.page.get_by_role("button", name="Sonraki iş filtresini kaldır").click()
        self.page.wait_for_url(f"{self.base}/raporlar")
        # Typing a search goes into the URL too.
        self.page.get_by_label("Leadlerde ara").fill(ready["name"])
        self.page.wait_for_url("**/raporlar?q=*")
        self.assertEqual(rows.count(), 1)
        self.assertEqual(self.errors, [])

    def test_csv_export_defuses_spreadsheet_formulas(self):
        lead = self.lead(0)
        original = lead.get("city")
        self.addCleanup(lead.__setitem__, "city", original)
        lead["city"] = '=HYPERLINK("http://example.com","x")'
        self.page.goto(f"{self.base}/raporlar")
        self.heading("Leadler")
        with self.page.expect_download() as download:
            self.page.get_by_role("button", name="Dışa aktar (CSV)").click()
        text = Path(download.value.path()).read_text(encoding="utf-8-sig")
        self.assertIn('"\'=HYPERLINK(""http://example.com"",""x"")"', text)
        self.assertNotIn(',"=HYPERLINK', text)
        self.assertTrue(text.startswith('"İşletme","Sektör","Şehir","Telefon"'))

    def test_workspace_card_selects_and_panel_links_to_the_lead(self):
        lead = self.lead(1)
        self.page.goto(f"{self.base}/")
        self.heading("Lead Workspace")
        card = self.page.get_by_role("button", name=lead["name"])
        card.click()
        self.assertEqual(card.get_attribute("aria-pressed"), "true")
        panel = self.page.get_by_role("complementary", name="Seçili lead")
        panel.get_by_role("link", name=lead["name"]).click()
        self.heading(lead["name"])
        self.assertEqual(self.page.evaluate("location.pathname"), f"/leads/{lead['lead_id']}")

    def test_sales_home_is_the_work_queue(self):
        from datetime import datetime, timedelta, timezone

        # One lead with a follow-up that was due two days ago.
        overdue = self.lead(2)
        original = overdue.get("workflow")
        self.addCleanup(overdue.__setitem__, "workflow", original)
        overdue["workflow"] = {
            **(overdue.get("workflow") or {}),
            "stage": "follow_up_due",
            "ready_to_contact": True,
            "follow_up_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
            "latest_contact_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
            "latest_outcome_label": "Ulaşılamadı",
        }
        self.session["user"] = self.sales
        self.page.goto(f"{self.base}/")
        self.heading("Bugün")
        self.assertEqual(self.page.get_by_role("link", name="Tarama merkezi").count(), 0)
        late = self.page.get_by_role("region", name="Geciken")
        late.get_by_role("heading", name=overdue["name"]).wait_for()
        late.get_by_text("Önceki sonuç: Ulaşılamadı").wait_for()
        late.get_by_role("button", name="Görüşmeye başla").click()
        self.page.get_by_role("dialog", name=overdue["name"]).wait_for()
        self.page.keyboard.press("Escape")
        self.page.get_by_role("dialog").wait_for(state="detached")
        first = self.page.get_by_role("region", name="İlk temas")
        first.get_by_role("heading", name=self.lead(0)["name"]).wait_for()
        check = self.page.get_by_role("region", name="Doğrulama gerekiyor").get_by_role("link", name="Kontrolü tamamla").first
        path = check.get_attribute("href")
        check.click()
        self.page.wait_for_url(f"{self.base}{path}")
        self.assertEqual(self.errors, [])

    def test_unsaved_note_stays_with_its_lead(self):
        first, second = self.lead(0), self.lead(1)
        self.page.goto(f"{self.base}/leads/{first['lead_id']}")
        self.heading(first["name"])
        self.page.get_by_role("tab", name="Aktivite").click()
        self.page.get_by_label("Not", exact=True).fill("Sadece ilk lead için")
        self.page.get_by_role("button", name="Sonraki").first.click()
        self.heading(second["name"])
        # The open tab carries over to the next lead; the note does not.
        self.assertEqual(self.page.get_by_role("tab", name="Aktivite").get_attribute("aria-selected"), "true")
        self.assertEqual(self.page.get_by_label("Not", exact=True).input_value(), "")
        self.page.get_by_role("button", name="Önceki").first.click()
        self.heading(first["name"])
        self.assertEqual(self.page.get_by_label("Not", exact=True).input_value(), "Sadece ilk lead için")

    def test_detail_tabs_follow_the_url_and_the_keyboard(self):
        lead = self.lead(0)
        original = lead.get("phone")
        self.addCleanup(lead.__setitem__, "phone", original)
        lead["phone"] = "0532 123 45 67"
        self.page.goto(f"{self.base}/leads/{lead['lead_id']}?sekme=iletisim")
        self.heading(lead["name"])
        tab = self.page.get_by_role("tab", name="İletişim")
        self.assertEqual(tab.get_attribute("aria-selected"), "true")
        tab.focus()
        self.page.keyboard.press("ArrowRight")
        self.page.wait_for_url("**?sekme=aktivite")
        self.assertTrue(self.page.get_by_role("tab", name="Aktivite").evaluate("node => node === document.activeElement"))
        self.page.get_by_role("tabpanel").get_by_label("Not", exact=True).wait_for()
        # A Turkish local number gets the country code in the WhatsApp link.
        self.assertEqual(self.page.get_by_role("link", name="WhatsApp").first.get_attribute("href"), "https://wa.me/905321234567")
        self.assertEqual(self.errors, [])

    def test_google_refresh_sends_only_the_lead_name(self):
        lead = self.lead(0)
        self.page.goto(f"{self.base}/leads/{lead['lead_id']}")
        self.heading(lead["name"])
        self.page.get_by_role("tab", name="Araştırma").click()
        self.page.get_by_role("button", name="Google verisini yenile").click()
        self.page.get_by_text("Google verisi kayıtlı işletme üzerinden yenilendi.").first.wait_for()
        self.assertEqual(self.place_posts, [{"lead_name": lead["name"]}])
        self.assertEqual(self.errors, [])

    def test_pipeline_card_moves_without_drag_and_failures_show(self):
        lead = self.lead(4)
        self.page.goto(f"{self.base}/pipeline")
        self.heading("Satış kanalı")
        self.page.get_by_label(f"{lead['name']} aşaması").select_option("won")
        for _ in range(50):  # the request is sent after the select changes
            if self.outreach_posts:
                break
            self.page.wait_for_timeout(100)
        self.assertEqual([post["action"] for post in self.outreach_posts], ["deal_won"])
        self.assertEqual(self.outreach_posts[0]["lead_name"], lead["name"])

        self.outreach_statuses = [503]
        other = self.lead(5)
        self.page.get_by_label(f"{other['name']} aşaması").select_option("lost")
        self.page.get_by_role("alert").filter(has_text=f"{other['name']} taşınamadı").wait_for()

    def test_team_editor_retains_form_on_error_and_refreshes_conflict(self):
        self.team_statuses = [503,409]
        self.page.goto(f"{self.base}/team")
        self.heading("Ekip yönetimi")
        card = self.page.locator("li").filter(has=self.page.get_by_role("heading",name=self.sales['name'],exact=True))
        card.get_by_role("button",name="Düzenle",exact=True).click()
        dialog = self.page.get_by_role("dialog",name="Ekip üyesini düzenle")
        dialog.get_by_label("Unvan (isteğe bağlı)").fill("Müşteri ilişkileri")
        dialog.get_by_label("Rol",exact=True).select_option('admin')
        dialog.get_by_label("Aktif hesap").uncheck()
        dialog.get_by_role("button",name="Kaydet",exact=True).click()
        dialog.get_by_role("alert").wait_for()
        self.assertEqual(dialog.get_by_label("Unvan (isteğe bağlı)").input_value(),"Müşteri ilişkileri")
        dialog.get_by_role("button",name="Kaydet",exact=True).click()
        dialog.get_by_role("button",name="Güncel bilgileri al").click()
        dialog.get_by_text("Güncel hesap alındı.",exact=False).wait_for()
        self.assertEqual(dialog.get_by_label("Rol",exact=True).input_value(),'admin')
        self.assertFalse(dialog.get_by_label("Aktif hesap").is_checked())
        dialog.get_by_role("button",name="Kaydet",exact=True).click()
        dialog.wait_for(state='detached')
        self.assertEqual(self.team_posts[0]['idempotency_key'],self.team_posts[1]['idempotency_key'])
        self.assertNotEqual(self.team_posts[1]['idempotency_key'],self.team_posts[2]['idempotency_key'])
        self.assertEqual(self.team_posts[2]['expected_updated_at'],'2026-10-10T07:01:00Z')

    def test_account_password_and_density_are_real_preferences(self):
        self.page.goto(f"{self.base}/profile")
        self.heading("Hesabım ve ayarlar")
        self.page.get_by_label("Lead listesindeki satır aralığı").select_option('compact')
        self.page.reload()
        self.assertEqual(self.page.get_by_label("Lead listesindeki satır aralığı").input_value(),'compact')
        self.assertEqual(self.page.locator('html').get_attribute('data-density'),'compact')
        self.password_status = 400
        self.page.get_by_label("Mevcut şifre",exact=True).fill('wrong')
        self.page.get_by_label("Yeni şifre",exact=True).fill('Synthetic new password')
        self.page.get_by_label("Yeni şifre tekrar",exact=True).fill('Synthetic new password')
        self.page.get_by_role("button",name="Şifreyi değiştir").click()
        self.page.get_by_role("alert").get_by_text("Mevcut şifre doğru değil.").wait_for()
        self.assertEqual(self.page.get_by_label("Yeni şifre",exact=True).input_value(),'Synthetic new password')
        self.password_status = 200
        self.page.get_by_role("button",name="Şifreyi değiştir").click()
        self.page.get_by_text("Şifren değiştirildi. Yeni şifrenle tekrar giriş yap.").wait_for()
        self.page.get_by_placeholder("ad@zeplinmedia.com").wait_for()
        self.assertEqual(len(self.password_posts),2)

    def test_team_sales_guard_and_services_without_leads(self):
        self.session['user'] = self.sales
        self.page.goto(f"{self.base}/team")
        self.page.get_by_text("Bu ekran yalnız yöneticilere açık.").wait_for()
        self.assertEqual(self.page.get_by_role("button",name="Kişi ekle").count(),0)
        self.payload['leads'] = []
        self.page.goto(f"{self.base}/hizmetler")
        self.heading("Zeplin Media Hizmetleri")
        self.page.get_by_text("Kapsam ve keşif soruları",exact=True).first.click()
        self.page.get_by_role("heading",name="Keşifte sor",exact=True).first.wait_for()
        self.assertEqual(self.errors,[])

    def test_phone_layout_has_bottom_bar_and_menu(self):
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.page.goto(f"{self.base}/")
        self.heading("Lead Workspace")
        quick = self.page.get_by_role("navigation", name="Hızlı menü")
        quick.get_by_role("link", name="Leadler").click()
        self.heading("Leadler")
        quick.get_by_role("button", name="Menü").click()
        menu = self.page.get_by_role("dialog", name="Menü")
        menu.get_by_role("link", name="Hizmetler").click()
        menu.wait_for(state="detached")
        self.heading("Zeplin Media Hizmetleri")
        # Nothing wider than the screen.
        widest = self.page.evaluate("Math.max(...[...document.querySelectorAll('body *')].map(e => e.getBoundingClientRect().right))")
        self.assertLessEqual(widest, 390)
        self.assertEqual(self.errors, [])

    def test_slash_opens_search(self):
        self.page.goto(f"{self.base}/")
        self.heading("Lead Workspace")
        self.page.keyboard.press("/")
        self.page.get_by_role("dialog", name="Lead ara").wait_for()

    def test_reports_show_definitions_and_link_to_the_list(self):
        self.page.goto(f"{self.base}/analytics")
        self.heading("Raporlar")
        self.assertEqual(self.metric_periods, ["30"])
        # A status distribution, never called a funnel.
        self.page.get_by_role("heading", name="Durum dağılımı").wait_for()
        self.assertEqual(self.page.get_by_text("Dönüşüm Hunisi", exact=True).count(), 0)
        self.page.get_by_text("aynı işletme iki kez sayılmaz").wait_for()
        self.page.get_by_role("group", name="Dönem").get_by_role("button", name="7 gün").click()
        self.page.wait_for_url("**/analytics?donem=7")
        self.page.get_by_text("Son 7 gün (bugün dahil)").first.wait_for()
        self.assertIn("7", self.metric_periods)
        self.page.get_by_role("link", name="Yeni", exact=True).click()
        self.page.wait_for_url("**/raporlar?asama=yeni")
        self.heading("Leadler")
        self.assertEqual(self.errors, [])

    def test_no_runtime_compiler_or_third_party_scripts(self):
        self.page.goto(f"{self.base}/")
        self.page.wait_for_load_state("networkidle")
        html = (PUBLIC / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("text/babel", html)
        self.assertNotIn("unpkg.com", html)
        scripts = self.page.evaluate("[...document.scripts].map(s => s.src).filter(Boolean)")
        self.assertTrue(scripts and all(src.startswith(self.base) for src in scripts), scripts)
        self.assertFalse([url for url in self.external if "unpkg" in url or "babel" in url])


if __name__ == "__main__":
    unittest.main()
