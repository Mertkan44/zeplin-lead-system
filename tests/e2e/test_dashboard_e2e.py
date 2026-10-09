"""End-to-end checks of the built dashboard (public/) in Chromium.

The page is served from public/ with the same fallback and Content-Security-
Policy header Vercel uses (unknown paths get index.html, so a CSP violation
shows up as a console error); the API is mocked in the browser, with the workspace
payload produced by the real api/workspace.py handler from the synthetic
sample leads. Runs only with RUN_E2E=1 (CI's e2e job):

    RUN_E2E=1 python -m unittest discover -s tests/e2e

Set E2E_CHROMIUM_PATH to use an already installed Chromium.
"""

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
        cls.admin = {"email": "boss@example.com", "name": "Boss", "role": "admin"}
        cls.sales = {"email": "seller@example.com", "name": "Satış Kişisi", "role": "sales"}
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
        self.page = self.browser.new_page(viewport={"width": 1280, "height": 900})
        self.errors, self.external = [], []
        self.session = {"user": self.admin}
        self.workspace_status = 200
        self.status_save_status = 200
        self.outreach_statuses = []  # status codes for the next POST /api/outreach calls
        self.outreach_posts = []
        self.place_posts = []
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
        self.page.get_by_text("Profil", exact=True).first.click()
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
            "/profile": "Ekip ve hesap",
            "/admin": "Search operasyonu",
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
        self.page.get_by_role("button", name="Kazanıldı", exact=True).click()
        self.page.get_by_role("alert").filter(has_text="Durum kaydedilemedi.").wait_for(timeout=10000)
        statuses = self.page.get_by_role("group", name="Pipeline durumu")
        self.assertEqual(statuses.get_by_role("button", name="Kazanıldı").get_attribute("aria-pressed"), "false")
        self.assertEqual(statuses.get_by_role("button", name="Yeni").get_attribute("aria-pressed"), "true")

    def test_theme_is_the_only_thing_kept_in_browser_storage(self):
        self.page.goto(f"{self.base}/leads/{self.lead(0)['lead_id']}")
        self.heading(self.lead(0)["name"])
        self.page.get_by_role("button", name="Aydınlık moda geç").click()
        self.page.reload()
        self.heading(self.lead(0)["name"])
        self.assertEqual(self.page.evaluate("document.documentElement.dataset.theme"), "light")
        self.assertEqual(self.page.evaluate("Object.keys(localStorage)"), ["zeplin_theme"])
        self.assertEqual(self.page.evaluate("Object.keys(sessionStorage)"), [])

    def test_contact_result_keeps_the_form_on_failure_and_retries_once(self):
        lead = self.lead(0)
        self.outreach_statuses = [503]
        self.page.goto(f"{self.base}/leads/{lead['lead_id']}")
        self.heading(lead["name"])
        self.page.get_by_role("button", name="Temas ekranı", exact=True).click()
        dialog = self.page.get_by_role("dialog", name=lead["name"])
        dialog.wait_for()
        dialog.get_by_role("button", name="Ulaşılamadı", exact=True).click()
        dialog.get_by_label("Görüşme notu").fill("Telefon kapalıydı")
        dialog.get_by_role("button", name="Sonucu ve görevi kaydet").click()
        dialog.get_by_role("alert").wait_for()
        # Nothing typed or chosen is lost.
        self.assertEqual(dialog.get_by_label("Görüşme notu").input_value(), "Telefon kapalıydı")
        self.assertEqual(dialog.get_by_role("button", name="Ulaşılamadı", exact=True).get_attribute("aria-pressed"), "true")
        dialog.get_by_role("button", name="Sonucu ve görevi kaydet").click()
        dialog.wait_for(state="detached")
        first, retry = self.outreach_posts
        self.assertEqual(first["idempotency_key"], retry["idempotency_key"])
        self.assertEqual((retry["outcome"], retry["note"], retry["lead_name"]), ("no_answer", "Telefon kapalıydı", lead["name"]))
        # The browser logs the simulated 503 itself; nothing else may fail.
        self.assertEqual([e for e in self.errors if "status of 503" not in e], [])

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
        self.session["user"] = self.sales
        self.page.goto(f"{self.base}/")
        self.heading("Bugünkü İşlerim")
        self.assertEqual(self.page.get_by_role("link", name="Admin").count(), 0)
        self.page.get_by_role("button", name="Aramaya hazır").click()
        self.page.get_by_role("button", name="Temas ekranı").first.click()
        self.page.get_by_role("dialog").wait_for()
        self.page.keyboard.press("Escape")
        self.page.get_by_role("dialog").wait_for(state="detached")
        self.page.get_by_role("button", name="Kontrol", exact=False).first.click()
        queue_item = self.page.get_by_role("link", name="Kontrolü tamamla").first
        path = queue_item.get_attribute("href")
        queue_item.click()
        self.page.wait_for_url(f"{self.base}{path}")
        self.assertEqual(self.errors, [])

    def test_unsaved_note_stays_with_its_lead(self):
        first, second = self.lead(0), self.lead(1)
        self.page.goto(f"{self.base}/leads/{first['lead_id']}")
        self.heading(first["name"])
        self.page.get_by_label("Hızlı not").fill("Sadece ilk lead için")
        self.page.get_by_role("button", name="Sonraki").first.click()
        self.heading(second["name"])
        self.assertEqual(self.page.get_by_label("Hızlı not").input_value(), "")
        self.page.get_by_role("button", name="Önceki").first.click()
        self.heading(first["name"])
        self.assertEqual(self.page.get_by_label("Hızlı not").input_value(), "Sadece ilk lead için")

    def test_google_refresh_sends_only_the_lead_name(self):
        lead = self.lead(0)
        self.page.goto(f"{self.base}/leads/{lead['lead_id']}")
        self.heading(lead["name"])
        self.page.get_by_role("button", name="Google verisini yenile").click()
        self.page.get_by_text("Google verisi kayıtlı işletme üzerinden yenilendi.").first.wait_for()
        self.assertEqual(self.place_posts, [{"lead_name": lead["name"]}])
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
