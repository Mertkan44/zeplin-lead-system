"""Report metrics (WP11): numerator and denominator of every number on a fixed
fixture, including midnight in Istanbul, no data, old analyses, closed leads,
several contacts with one business and a repeated win."""

import unittest
from datetime import datetime, timezone

from src.metrics import build_metrics, parse_time, period_bounds, sector_label

# Saturday 2026-10-10 15:00 in Istanbul (UTC+3).
NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


def lead(lead_id, name, *, status="yeni", score=70, grade="B", score_status="reliable", created_at=None,
         last_analyzed="2026-10-01 10:00", sector="restaurant", category="Kafe", coverage=60):
    return {
        "lead_id": lead_id,
        "name": name,
        "status": status,
        "sector": sector,
        "category": category,
        "created_at": created_at or "2026-10-01T07:00:00+00:00",
        "last_analyzed": last_analyzed,
        "scoring": {"score": score, "grade": grade, "score_status": score_status, "coverage": coverage},
    }


def result(event_id, lead_name, outcome, happened_at):
    return {"id": event_id, "lead_name": lead_name, "action": "contact_result_recorded", "outcome": outcome, "happened_at": happened_at}


LEADS = [
    lead(1, "Kafe A"),
    lead(2, "Kafe B", status="converted", score=90, grade="A"),
    lead(3, "Klinik C", status="follow_up", score=40, grade="C", sector="health", category="Diş kliniği"),
    lead(4, "Berber D", status="lost", sector="", category="Berber", score=None, score_status="insufficient", coverage=20),
    # Added long ago and analysed again yesterday: an analysis, not a new lead.
    lead(5, "Eski E", created_at="2026-01-05T09:00:00+00:00", last_analyzed="2026-10-09 18:00", sector="automotive", category="Oto yıkama"),
]

EVENTS = [
    # Kafe A: two calls in the period, one interested.
    result(1, "Kafe A", "no_answer", "2026-10-08T07:00:00+00:00"),
    result(2, "Kafe A", "reached_interested", "2026-10-09T07:00:00+00:00"),
    # Kafe B: won, and the win recorded twice by mistake.
    result(3, "Kafe B", "won", "2026-10-09T08:00:00+00:00"),
    result(4, "Kafe B", "won", "2026-10-09T08:05:00+00:00"),
    # Klinik C: 00:30 Istanbul on Oct 4 is still Oct 3 in UTC.
    result(5, "Klinik C", "proposal_requested", "2026-10-03T21:30:00+00:00"),
    # Berber D: lost; a note is not a result.
    result(6, "Berber D", "not_interested", "2026-10-02T09:00:00+00:00"),
    {"id": 7, "lead_name": "Kafe A", "action": "note_added", "happened_at": "2026-10-09T09:00:00+00:00"},
    # An event of a lead the user cannot see.
    result(8, "Başkasının", "won", "2026-10-09T09:00:00+00:00"),
    # Last month.
    result(9, "Kafe A", "no_answer", "2026-09-01T09:00:00+00:00"),
]

STATES = {
    1: {"latest_follow_up_at": "2026-10-11T07:00:00+00:00"},  # tomorrow 10:00
    3: {"latest_follow_up_at": "2026-10-09T07:00:00+00:00"},  # yesterday: overdue
    2: {"latest_follow_up_at": "2026-10-01T07:00:00+00:00"},  # closed lead: not counted
    5: {"latest_follow_up_at": "2026-10-10T20:59:00+00:00"},  # 23:59 Istanbul today
}


class PeriodTests(unittest.TestCase):
    def test_periods_start_at_istanbul_midnight_and_include_today(self):
        start, end = period_bounds("7", NOW)
        self.assertEqual(start.isoformat(), "2026-10-03T21:00:00+00:00")  # Oct 4 00:00 Istanbul
        self.assertEqual(end.isoformat(), "2026-10-10T21:00:00+00:00")  # Oct 11 00:00 Istanbul
        self.assertEqual(period_bounds("all", NOW)[0], None)
        with self.assertRaises(ValueError):
            period_bounds("365", NOW)

    def test_local_analysis_stamps_are_istanbul_time(self):
        self.assertEqual(parse_time("2026-10-01 10:00").isoformat(), "2026-10-01T07:00:00+00:00")
        self.assertIsNone(parse_time("dün"))


class SalesMetricTests(unittest.TestCase):
    def metrics(self, period="30"):
        return build_metrics(LEADS, EVENTS, STATES, period=period, now=NOW)

    def test_contacts_count_businesses_and_results_separately(self):
        sales = self.metrics()["sales"]
        self.assertEqual(sales["contacted_businesses"]["value"], 4)  # A, B, C, D
        self.assertEqual(sales["contact_results"]["value"], 6)  # 2 + 2 + 1 + 1; notes and others excluded

    def test_interest_proposal_win_and_loss_are_distinct_businesses(self):
        sales = self.metrics()["sales"]
        self.assertEqual(sales["interested_businesses"]["value"], 2)  # A, C
        self.assertEqual(sales["proposal_businesses"]["value"], 1)  # C
        self.assertEqual(sales["won_businesses"]["value"], 1)  # B once, despite two records
        self.assertEqual(sales["lost_businesses"]["value"], 1)  # D
        outcomes = {item["key"]: item["count"] for item in sales["outcomes"]}
        self.assertEqual(outcomes["won"], 2)  # the outcome table counts records

    def test_the_period_edge_follows_istanbul_midnight(self):
        sales = self.metrics("7")["sales"]
        # Klinik C at 00:30 Oct 4 Istanbul is inside "last 7 days"; Berber D (Oct 2) is not.
        self.assertEqual(sales["contacted_businesses"]["value"], 3)
        self.assertEqual(sales["proposal_businesses"]["value"], 1)
        self.assertEqual(sales["lost_businesses"]["value"], 0)

    def test_all_time_includes_last_month(self):
        self.assertEqual(self.metrics("all")["sales"]["contact_results"]["value"], 7)


class TaskAndStatusTests(unittest.TestCase):
    def test_follow_ups_skip_closed_leads_and_split_by_istanbul_day(self):
        tasks = build_metrics(LEADS, EVENTS, STATES, period="30", now=NOW)["tasks"]
        self.assertEqual(tasks["overdue"]["value"], 1)  # Klinik C
        self.assertEqual(tasks["due_today"]["value"], 1)  # Eski E at 23:59 today
        self.assertEqual(tasks["upcoming"]["value"], 1)  # Kafe A tomorrow

    def test_status_distribution_is_current_state_not_a_funnel(self):
        statuses = build_metrics(LEADS, [], {}, period="7", now=NOW)["statuses"]
        self.assertEqual(statuses["label"], "Durum dağılımı")
        counts = {item["key"]: item["count"] for item in statuses["items"]}
        self.assertEqual(counts, {"yeni": 2, "missing_info": 0, "ready": 0, "contacted": 0, "follow_up": 1, "converted": 1, "lost": 1})
        self.assertIn("dönüşüm hunisi değildir", statuses["definition"])


class ResearchMetricTests(unittest.TestCase):
    def test_new_leads_use_created_at_and_reanalysis_is_counted_apart(self):
        research = build_metrics(LEADS, [], {}, period="7", now=NOW)["research"]
        self.assertEqual(research["new_leads"]["value"], 0)  # all added Oct 1 or earlier
        self.assertEqual(research["analyzed_leads"]["value"], 1)  # Eski E, analysed Oct 9
        research = build_metrics(LEADS, [], {}, period="30", now=NOW)["research"]
        self.assertEqual(research["new_leads"]["value"], 4)
        self.assertEqual(research["analyzed_leads"]["value"], 5)

    def test_unknown_scores_are_left_out_not_zero(self):
        score = build_metrics(LEADS, [], {}, period="30", now=NOW)["research"]["average_score"]
        self.assertEqual((score["value"], score["sample"], score["excluded"]), (round((70 + 90 + 40 + 70) / 4), 4, 1))

    def test_grades_and_sectors_keep_every_lead(self):
        research = build_metrics(LEADS, [], {}, period="30", now=NOW)["research"]
        self.assertEqual({item["key"]: item["count"] for item in research["grades"]["items"]}, {"A": 1, "B": 2, "C": 1, "D": 0})
        self.assertEqual(research["grades"]["unscored"], 1)
        sectors = {item["label"]: item["count"] for item in research["sectors"]["items"]}
        self.assertEqual(sectors, {"Restoran ve Kafe": 2, "Güzellik ve Bakım": 1, "Otomotiv": 1, "Sağlık ve Klinik": 1})
        self.assertEqual(sum(sectors.values()), research["sectors"]["total"])

    def test_more_than_five_sectors_fold_into_other(self):
        many = [lead(index, f"L{index}", sector=sector, category="") for index, sector in enumerate(
            ["restaurant", "retail", "health", "salon", "auto", "fitness", "fitness"], start=1)]
        sectors = build_metrics(many, [], {}, period="30", now=NOW)["research"]["sectors"]
        self.assertEqual(sectors["items"][-1], {"label": "Diğer", "count": 2})
        self.assertEqual(sum(item["count"] for item in sectors["items"]), 7)

    def test_sector_label_reads_aliases_and_categories(self):
        self.assertEqual(sector_label({"sector": "beauty"}), "Güzellik ve Bakım")
        self.assertEqual(sector_label({"sector": "", "category": "Veteriner"}), "Sağlık ve Klinik")
        self.assertEqual(sector_label({"sector": "fitness", "category": "Spor salonu"}), "Diğer")


class EmptyAndWeeklyTests(unittest.TestCase):
    def test_no_data_gives_zeros_and_unknowns_not_fake_values(self):
        metrics = build_metrics([], [], {}, period="30", now=NOW)
        self.assertEqual(metrics["lead_count"], 0)
        self.assertEqual(metrics["sales"]["contacted_businesses"]["value"], 0)
        self.assertIsNone(metrics["research"]["average_score"]["value"])
        self.assertIsNone(metrics["research"]["average_coverage"]["value"])
        self.assertEqual(metrics["research"]["sectors"]["items"], [])
        self.assertEqual(metrics["weekly"]["new_leads"], [0] * 8)

    def test_weekly_series_start_on_istanbul_mondays(self):
        weekly = build_metrics(LEADS, EVENTS, {}, period="7", now=NOW)["weekly"]
        self.assertEqual(weekly["weeks"][-1], "2026-10-05")  # Monday of this week
        self.assertEqual(len(weekly["weeks"]), 8)
        self.assertEqual(weekly["new_leads"][-2], 4)  # added Oct 1, the week of Sep 28
        # This week: Kafe A ×2, Kafe B ×2 and Klinik C (Oct 4 00:30 Istanbul is Sunday → last week).
        self.assertEqual(weekly["contact_results"][-1], 4)
        self.assertEqual(weekly["contact_results"][-2], 2)  # Klinik C and Berber D


if __name__ == "__main__":
    unittest.main()
