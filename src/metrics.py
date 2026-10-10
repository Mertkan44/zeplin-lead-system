"""Reporting metrics (review §10, WP11): one definition per number.

Every metric says which date it counts by and what its scope is; days start
at midnight Europe/Istanbul. Current-state numbers (status distribution,
follow-ups, scores) are "now"; activity numbers count inside the period.
Status counts are a distribution; opportunity history is not a cohort funnel.
Pure functions: callers pass leads, events and states.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, time, timedelta, timezone
from typing import Any, Iterable

from src.workflow import BUSINESS_TIMEZONE

PERIODS = {"7": 7, "30": 30, "90": 90, "all": None}

INTERESTED_OUTCOMES = {"reached_interested", "proposal_requested"}
LOST_OUTCOMES = {"lost", "not_interested"}
CLOSED_STATUSES = {"converted", "lost"}

STATUS_LABELS = {
    "yeni": "Yeni",
    "missing_info": "Veri eksik",
    "ready": "Hazır",
    "contacted": "Temasta",
    "follow_up": "Takipte",
    "converted": "Kazanıldı",
    "lost": "Kaybedildi",
}

OUTCOME_LABELS = {
    "reached_interested": "İlgilendi",
    "proposal_requested": "Teklif istedi",
    "reached_later": "Daha sonra görüşülecek",
    "no_answer": "Ulaşılamadı",
    "wrong_number": "Numara yanlış",
    "not_interested": "İlgilenmedi",
    "won": "Anlaşma yapıldı",
    "lost": "Fırsat kaybedildi",
}

SECTOR_LABELS = {
    "restaurant": "Restoran ve Kafe",
    "retail": "Perakende ve Mağaza",
    "health": "Sağlık ve Klinik",
    "salon": "Güzellik ve Bakım",
    "auto": "Otomotiv",
}
OTHER_SECTOR = "Diğer"
TOP_SECTORS = 5
WEEKS = 8


def parse_time(value: Any) -> datetime | None:
    """ISO text (or "YYYY-MM-DD HH:MM") to an aware UTC datetime; None if unreadable."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace(" ", "T").replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # Analysis stamps are written in local business time without an offset.
        parsed = parsed.replace(tzinfo=BUSINESS_TIMEZONE)
    return parsed.astimezone(timezone.utc)


def business_day_start(moment: datetime) -> datetime:
    """Midnight Europe/Istanbul of the day `moment` falls on, as UTC."""
    local = moment.astimezone(BUSINESS_TIMEZONE)
    return datetime.combine(local.date(), time.min, tzinfo=BUSINESS_TIMEZONE).astimezone(timezone.utc)


def period_bounds(period: str, now: datetime) -> tuple[datetime | None, datetime]:
    """[start, end) of a period; "7" = today and the six days before it."""
    if period not in PERIODS:
        raise ValueError("period must be one of 7, 30, 90, all")
    days = PERIODS[period]
    end = business_day_start(now) + timedelta(days=1)
    return (None if days is None else end - timedelta(days=days)), end


def _within(moment: datetime | None, start: datetime | None, end: datetime) -> bool:
    return moment is not None and moment < end and (start is None or moment >= start)


def _metric(value: Any, label: str, definition: str, **extra: Any) -> dict[str, Any]:
    return {"value": value, "label": label, "definition": definition, **extra}


SECTOR_ALIASES = {"automotive": "auto", "beauty": "salon"}

# Category words → sector, for leads stored without a known sector (same rule
# as web/src/domain/lead.ts canonicalSector).
_CATEGORY_SECTORS = [
    ("restaurant", re.compile(r"restoran|restaurant|cafe|kafe|coffee|bistro|lokanta|pastane|fırın|bakery|meyhane")),
    ("health", re.compile(r"diş|dental|dentist|klinik|clinic|doktor|sağlık|eczane|optik|veteriner")),
    ("salon", re.compile(r"kuaför|güzellik|beauty|spa|nail|berber|brow|lash|pilates|yoga|masaj")),
    ("auto", re.compile(r"oto|otomotiv|araba|araç|kaporta|lastik|galeri|garaj")),
    ("retail", re.compile(r"mağaza|market|butik|shop|store|giyim|perakende|çiçek|kitap|mobilya|depo")),
]


def sector_label(lead: dict[str, Any]) -> str:
    stored = str(lead.get("sector") or "").strip().lower()
    stored = SECTOR_ALIASES.get(stored, stored)
    if stored in SECTOR_LABELS:
        return SECTOR_LABELS[stored]
    category = str(lead.get("category") or "").lower()
    for key, pattern in _CATEGORY_SECTORS:
        if pattern.search(category):
            return SECTOR_LABELS[key]
    return OTHER_SECTOR


def _score_available(lead: dict[str, Any]) -> bool:
    scoring = lead.get("scoring") or {}
    return (scoring.get("score_status") or "insufficient") != "insufficient" and scoring.get("score") is not None


def _week_start(moment: datetime) -> datetime:
    """Monday 00:00 Europe/Istanbul of the week `moment` falls in, as UTC."""
    day = business_day_start(moment)
    local = day.astimezone(BUSINESS_TIMEZONE)
    return (local - timedelta(days=local.weekday())).astimezone(timezone.utc)


def build_metrics(
    leads: list[dict[str, Any]],
    events: Iterable[dict[str, Any]],
    states: dict[Any, dict[str, Any]],
    *,
    period: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Metrics for the leads the user can read.

    `events` are outreach events (at least those inside the period and the
    last WEEKS weeks); `states` map lead_id → lead_activity_state row.
    """
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start, end = period_bounds(period, now)
    today = business_day_start(now)
    tomorrow = today + timedelta(days=1)
    lead_names = {lead.get("name") for lead in leads}
    status_of = {lead.get("name"): lead.get("status") or "yeni" for lead in leads}

    results = [
        event for event in events
        if event.get("action") == "contact_result_recorded" and event.get("lead_name") in lead_names
    ]
    in_period = [event for event in results if _within(parse_time(event.get("happened_at")), start, end)]
    commercial_closures = [event for event in events
        if event.get("action") == "opportunity_stage_changed" and event.get("lead_name") in lead_names
        and _within(parse_time(event.get("happened_at")), start, end)]

    def closed_businesses(outcomes: set[str]) -> int:
        return len({event.get("lead_name") for event in [*in_period, *commercial_closures] if event.get("outcome") in outcomes})

    def businesses(outcomes: set[str] | None = None) -> int:
        return len({
            event.get("lead_name") for event in in_period
            if outcomes is None or event.get("outcome") in outcomes
        })

    outcome_counts = Counter(event.get("outcome") for event in in_period)

    # Follow-ups: the latest result of each open lead decides its next date.
    overdue = due_today = upcoming = 0
    for lead in leads:
        if status_of.get(lead.get("name")) in CLOSED_STATUSES:
            continue
        state = states.get(lead.get("lead_id")) or {}
        follow_up = parse_time(state.get("latest_follow_up_at"))
        if follow_up is None:
            continue
        if follow_up < today:
            overdue += 1
        elif follow_up < tomorrow:
            due_today += 1
        else:
            upcoming += 1

    status_counts = Counter(status_of.values())
    statuses = [
        {"key": key, "label": label, "count": status_counts.get(key, 0)}
        for key, label in STATUS_LABELS.items()
    ]

    scored = [lead for lead in leads if _score_available(lead)]
    average = round(sum(int(lead["scoring"]["score"]) for lead in scored) / len(scored)) if scored else None
    grade_counts = Counter((lead.get("scoring") or {}).get("grade") for lead in scored)
    grades = [{"key": grade, "count": grade_counts.get(grade, 0)} for grade in ("A", "B", "C", "D")]

    sector_counts = Counter(sector_label(lead) for lead in leads)
    named = sorted(((name, count) for name, count in sector_counts.items() if name != OTHER_SECTOR), key=lambda item: (-item[1], item[0]))
    top, rest = named[:TOP_SECTORS], named[TOP_SECTORS:]
    other = sector_counts.get(OTHER_SECTOR, 0) + sum(count for _, count in rest)
    sectors = [{"label": name, "count": count} for name, count in top]
    if other:
        sectors.append({"label": OTHER_SECTOR, "count": other})

    new_leads = sum(1 for lead in leads if _within(parse_time(lead.get("created_at")), start, end))
    analyzed = sum(1 for lead in leads if _within(parse_time(lead.get("last_analyzed")), start, end))
    coverages = [int((lead.get("scoring") or {}).get("coverage") or 0) for lead in leads if (lead.get("scoring") or {}).get("coverage") is not None]

    this_week = _week_start(now)
    week_starts = [this_week - timedelta(weeks=offset) for offset in range(WEEKS - 1, -1, -1)]

    def weekly(times: list[datetime | None]) -> list[int]:
        counts = Counter(_week_start(moment) for moment in times if moment is not None)
        return [counts.get(week, 0) for week in week_starts]

    period_label = "Tüm zamanlar" if start is None else f"Son {PERIODS[period]} gün (bugün dahil)"
    return {
        "period": {
            "key": period,
            "label": period_label,
            "start": start.isoformat() if start else None,
            "end": end.isoformat(),
            "timezone": "Europe/Istanbul",
        },
        "lead_count": len(leads),
        "sales": {
            "contacted_businesses": _metric(businesses(), "Temas edilen işletme", "Dönemde en az bir görüşme sonucu kaydedilen farklı işletme."),
            "contact_results": _metric(len(in_period), "Görüşme sonucu", "Dönemde kaydedilen görüşme sonuçları; aynı işletmeyle tekrar görüşmeler ayrı sayılır."),
            "interested_businesses": _metric(businesses(INTERESTED_OUTCOMES), "İlgilenen işletme", "Dönemde “İlgilendi” veya “Teklif istedi” sonucu alan farklı işletme."),
            "proposal_businesses": _metric(businesses({"proposal_requested"}), "Teklif isteyen işletme", "Dönemde “Teklif istedi” sonucu alan farklı işletme."),
            "won_businesses": _metric(closed_businesses({"won"}), "Kazanılan işletme", "Dönemde görüşme sonucu veya fırsat geçişiyle kazanılan farklı işletme; aynı işletme iki kez sayılmaz. Tutar değil."),
            "lost_businesses": _metric(closed_businesses(LOST_OUTCOMES), "Kaybedilen işletme", "Dönemde görüşme sonucu veya fırsat geçişiyle kaybedilen farklı işletme."),
            "outcomes": [
                {"key": key, "label": label, "count": outcome_counts.get(key, 0)}
                for key, label in OUTCOME_LABELS.items()
            ],
        },
        "tasks": {
            "overdue": _metric(overdue, "Geciken takip", "Açık lead'lerde takip tarihi bugünden önce olanlar (şu an)."),
            "due_today": _metric(due_today, "Bugün takip", "Açık lead'lerde takip tarihi bugün olanlar (şu an)."),
            "upcoming": _metric(upcoming, "İleri tarihli takip", "Açık lead'lerde takip tarihi yarın ve sonrası olanlar (şu an)."),
        },
        "statuses": {
            "label": "Durum dağılımı",
            "definition": "Lead'lerin şu anki durumu; dönemden etkilenmez ve bir dönüşüm hunisi değildir. Ticari fırsatların aşamaları Pipeline ekranında ayrı tutulur.",
            "items": statuses,
        },
        "research": {
            "new_leads": _metric(new_leads, "Yeni lead", "Dönemde sisteme eklenen lead (eklenme tarihine göre)."),
            "analyzed_leads": _metric(analyzed, "Analiz edilen lead", "Dönemde son analizi yapılan lead; yeniden analiz yeni lead sayılmaz."),
            "average_score": _metric(
                average,
                "Ortalama dijital skor",
                "Skoru hesaplanabilen lead'lerin ortalaması (şu an); kanıtı yetersiz lead'ler 0 sayılmaz, hariç tutulur.",
                sample=len(scored),
                excluded=len(leads) - len(scored),
            ),
            "average_coverage": _metric(
                round(sum(coverages) / len(coverages)) if coverages else None,
                "Ortalama denetim kapsamı",
                "Denetimde sonuçlanabilen kontrollerin oranı, lead ortalaması (şu an).",
                sample=len(coverages),
            ),
            "grades": {"definition": "Skoru hesaplanabilen lead'lerin sınıfı (şu an).", "items": grades, "unscored": len(leads) - len(scored)},
            "sectors": {"definition": "Tüm lead'ler, kayıtlı sektöre göre; ilk beş dışındakiler “Diğer”de.", "items": sectors, "total": len(leads)},
        },
        "weekly": {
            "definition": "Son 8 hafta, pazartesiden pazartesiye (İstanbul saati). Dönem seçiminden etkilenmez.",
            "weeks": [week.astimezone(BUSINESS_TIMEZONE).date().isoformat() for week in week_starts],
            "new_leads": weekly([parse_time(lead.get("created_at")) for lead in leads]),
            "contact_results": weekly([parse_time(event.get("happened_at")) for event in results]),
        },
    }
