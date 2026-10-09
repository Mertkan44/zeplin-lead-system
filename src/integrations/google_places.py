"""Google Places (New) lookups for one lead, with an explicit match decision.

A lead that already has a place id (verified earlier, or the `!19s` id in its
Maps URL) is refreshed by id. Otherwise a text search runs and each candidate
must pass a location gate on its own: a matching name never outweighs an
address in another city. Results are one of:

- verified: one candidate passes the gates and no close rival exists;
- ambiguous: candidates need a human choice (close rivals, a same-name branch
  in another district, a phone/website match with a different name);
- not_matched: nothing usable came back;
- provider_error: the API call failed; earlier data is kept.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import quote

import httpx

from src.config import env
from src.lead_identity import domain_key, google_place_id, phone_key


PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"
_PLACE_FIELDS = [
    "id",
    "displayName",
    "formattedAddress",
    "googleMapsUri",
    "businessStatus",
    "nationalPhoneNumber",
    "rating",
    "userRatingCount",
    "websiteUri",
    "primaryType",
]
PLACES_FIELD_MASK = ",".join(f"places.{field}" for field in _PLACE_FIELDS)
PLACE_DETAILS_FIELD_MASK = ",".join(_PLACE_FIELDS)

MATCH_STATUSES = ("verified", "ambiguous", "not_matched", "provider_error")
NAME_THRESHOLD = 0.72
# A phone or website match proves identity even when the listed name differs.
EVIDENCE_NAME_THRESHOLD = 0.5
# A passing candidate this close to the best one is a real alternative.
AMBIGUITY_MARGIN = 10
MAX_CANDIDATES = 5


def is_configured() -> bool:
    return bool(env("GOOGLE_PLACES_API_KEY"))


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# The 81 provinces, normalized: an address naming one of these that is not the
# lead's province is in another city.
_PROVINCES = frozenset("""
adana adiyaman afyonkarahisar agri aksaray amasya ankara antalya ardahan artvin aydin
balikesir bartin batman bayburt bilecik bingol bitlis bolu burdur bursa canakkale
cankiri corum denizli diyarbakir duzce edirne elazig erzincan erzurum eskisehir
gaziantep giresun gumushane hakkari hatay igdir isparta istanbul izmir kahramanmaras
karabuk karaman kars kastamonu kayseri kilis kirikkale kirklareli kirsehir kocaeli
konya kutahya malatya manisa mardin mersin mugla mus nevsehir nigde ordu osmaniye
rize sakarya samsun sanliurfa siirt sinop sirnak sivas tekirdag tokat trabzon tunceli
usak van yalova yozgat zonguldak
""".split())
# "... 34710 Kadıköy/İstanbul, Türkiye": district and province at the end of
# a Google Maps address.
_ADDRESS_AREA = re.compile(r"([^\s,/\d]+)\s*/\s*([^\s,/\d]+)\s*(?:,\s*T[üu]rkiye)?\s*$", re.IGNORECASE)


def _normalized(value: Any) -> str:
    # Turkish dotless ı has no decomposition; fold it like the audit does.
    raw = unicodedata.normalize("NFKD", str(value or "").casefold().replace("ı", "i"))
    ascii_value = "".join(char for char in raw if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", ascii_value))


def _name_similarity(expected: str, candidate: str) -> float:
    left = _normalized(expected)
    right = _normalized(candidate)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    return SequenceMatcher(None, left, right).ratio()


def _lead_location(lead: dict[str, Any]) -> tuple[str | None, list[str]]:
    """(province, district tokens) where the business is.

    The scraped Maps address ("... Kadıköy/İstanbul") says where the business
    is; `city` is the area that was scanned ("Istanbul Besiktas") and is only
    the fallback, since a scan can return businesses from nearby districts.
    """
    area = _ADDRESS_AREA.search(str(lead.get("address") or "").strip())
    if area:
        district, province = _normalized(area.group(1)), _normalized(area.group(2))
        if province in _PROVINCES and district:
            return province, district.split()
    tokens = [token for token in _normalized(lead.get("city")).split() if len(token) > 2]
    if not tokens:
        return None, []
    return tokens[0], tokens[1:]


def location_match(lead: dict[str, Any], candidate: dict[str, Any]) -> str:
    """district | province | conflict | unknown.

    conflict: the candidate's address names a different province. An address
    naming no province at all is unknown, not a conflict.
    """
    province, districts = _lead_location(lead)
    address = set(_normalized(candidate.get("formattedAddress")).split())
    if not province or not address:
        return "unknown"
    if province not in address:
        return "conflict" if address & (_PROVINCES - {province}) else "unknown"
    if districts and all(token in address for token in districts):
        return "district"
    return "province"


def _lead_website(lead: dict[str, Any]) -> Any:
    website = lead.get("website")
    return website.get("website_url") if isinstance(website, dict) else website


def assess_candidate(lead: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    display_name = (candidate.get("displayName") or {}).get("text") or ""
    name_score = _name_similarity(str(lead.get("name") or ""), display_name)
    location = location_match(lead, candidate)
    lead_phone = phone_key(lead.get("phone"))
    lead_domain = domain_key(_lead_website(lead))
    evidence = []
    if name_score >= NAME_THRESHOLD:
        evidence.append("name")
    if location in {"district", "province"}:
        evidence.append(f"location_{location}")
    if lead_phone and lead_phone == phone_key(candidate.get("nationalPhoneNumber")):
        evidence.append("phone")
    if lead_domain and lead_domain == domain_key(candidate.get("websiteUri")):
        evidence.append("website")
    strong = "phone" in evidence or "website" in evidence
    _, districts = _lead_location(lead)
    # Without a district on the lead, the province is all there is to match.
    full_location = location == "district" or (location == "province" and not districts)
    confidence = round(
        name_score * 60
        + (25 if full_location else 10 if location == "province" else 0)
        + (10 if "phone" in evidence else 0)
        + (5 if "website" in evidence else 0)
    )
    if location == "conflict":
        verdict, reason = "rejected", "location_conflict"
    elif full_location and (name_score >= NAME_THRESHOLD or (strong and name_score >= EVIDENCE_NAME_THRESHOLD)):
        verdict, reason = "match", None
    elif name_score >= NAME_THRESHOLD or strong:
        verdict = "review"
        reason = "other_district" if location == "province" and districts else (
            "location_unknown" if location == "unknown" else "name_differs"
        )
    else:
        verdict, reason = "rejected", "name_mismatch"
    return {
        "candidate": candidate,
        "verdict": verdict,
        "reason": reason,
        "confidence": min(100, confidence),
        "name_score": round(name_score, 2),
        "location_match": location,
        "evidence": evidence,
        "strong": strong,
    }


def _candidate_summary(assessment: dict[str, Any]) -> dict[str, Any]:
    candidate = assessment["candidate"]
    return {
        "place_id": candidate.get("id"),
        "display_name": (candidate.get("displayName") or {}).get("text"),
        "formatted_address": candidate.get("formattedAddress"),
        "phone": candidate.get("nationalPhoneNumber"),
        "website_url": candidate.get("websiteUri"),
        "maps_url": candidate.get("googleMapsUri"),
        "confidence": assessment["confidence"],
        "location_match": assessment["location_match"],
        "evidence": assessment["evidence"],
        "reason": assessment["reason"],
    }


def select_candidate(lead: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Decide among text-search candidates.

    Returns {"status": verified|ambiguous|not_matched, "match": assessment|None,
    "candidates": [summaries], "reason": str|None}.
    """
    assessed = sorted(
        (assess_candidate(lead, candidate) for candidate in candidates),
        key=lambda item: item["confidence"],
        reverse=True,
    )
    matches = [item for item in assessed if item["verdict"] == "match"]
    reviews = [item for item in assessed if item["verdict"] == "review"]
    if matches:
        best = matches[0]
        rivals = [
            item for item in matches[1:] + reviews
            if best["confidence"] - item["confidence"] < AMBIGUITY_MARGIN
        ]
        # Phone/website evidence settles a tie only when no rival has it too.
        settled = best["strong"] and not any(item["strong"] for item in rivals)
        if rivals and not settled:
            return {
                "status": "ambiguous",
                "match": None,
                "reason": "close_candidates",
                "candidates": [_candidate_summary(item) for item in [best, *rivals]][:MAX_CANDIDATES],
            }
        return {"status": "verified", "match": best, "reason": None, "candidates": []}
    if reviews:
        return {
            "status": "ambiguous",
            "match": None,
            "reason": reviews[0]["reason"],
            "candidates": [_candidate_summary(item) for item in reviews][:MAX_CANDIDATES],
        }
    conflict = any(
        item["reason"] == "location_conflict" and item["name_score"] >= NAME_THRESHOLD for item in assessed
    )
    return {
        "status": "not_matched",
        "match": None,
        "reason": "location_conflict" if conflict else ("name_mismatch" if assessed else "no_candidates"),
        "candidates": [],
    }


def _verified_result(
    candidate: dict[str, Any],
    *,
    method: str,
    assessment: dict[str, Any] | None,
    attempted_at: str,
    verified_by: str | None = None,
) -> dict[str, Any]:
    return {
        "status": "verified",
        "match_method": method,
        "verified_by": verified_by,
        "attempted_at": attempted_at,
        "refreshed_at": attempted_at,
        "place_id": candidate.get("id"),
        "display_name": (candidate.get("displayName") or {}).get("text"),
        "formatted_address": candidate.get("formattedAddress"),
        "maps_url": candidate.get("googleMapsUri"),
        "business_status": candidate.get("businessStatus"),
        "phone": candidate.get("nationalPhoneNumber"),
        "rating": candidate.get("rating"),
        "review_count": candidate.get("userRatingCount"),
        "website_url": candidate.get("websiteUri"),
        "primary_type": candidate.get("primaryType"),
        "match_confidence": (assessment or {}).get("confidence"),
        "location_match": (assessment or {}).get("location_match"),
        "match_evidence": (assessment or {}).get("evidence") or [],
    }


def _error_summary(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return type(exc).__name__


def _headers(api_key: str, field_mask: str) -> dict[str, str]:
    return {"Content-Type": "application/json", "X-Goog-Api-Key": api_key, "X-Goog-FieldMask": field_mask}


def _get_place(client: httpx.Client, api_key: str, place_id: str) -> dict[str, Any] | None:
    response = client.get(
        PLACES_DETAILS_URL.format(place_id=quote(place_id, safe="")),
        params={"languageCode": "tr", "regionCode": "TR"},
        headers=_headers(api_key, PLACE_DETAILS_FIELD_MASK),
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def _text_search(client: httpx.Client, api_key: str, query: str) -> list[dict[str, Any]]:
    response = client.post(
        PLACES_TEXT_SEARCH_URL,
        headers=_headers(api_key, PLACES_FIELD_MASK),
        json={"textQuery": query, "pageSize": MAX_CANDIDATES, "languageCode": "tr", "regionCode": "TR"},
    )
    response.raise_for_status()
    return response.json().get("places") or []


def search_place(
    lead: dict[str, Any],
    *,
    place_id: str | None = None,
    verified_by: str | None = None,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Look one lead up. `place_id` is a person's choice among ambiguous
    candidates; without it the lead's own place id is used when it has one."""
    api_key = env("GOOGLE_PLACES_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_PLACES_API_KEY is not configured")
    query = ", ".join(
        str(value).strip() for value in (lead.get("name"), lead.get("address"), lead.get("city")) if value
    )
    attempted_at = _now()
    known_id = place_id or google_place_id(lead)
    owns_client = client is None
    client = client or httpx.Client(timeout=20)
    try:
        if known_id:
            place = _get_place(client, api_key, known_id)
            if place:
                return _verified_result(
                    place,
                    method="manual_selection" if place_id else "place_id",
                    assessment=assess_candidate(lead, place),
                    attempted_at=attempted_at,
                    verified_by=verified_by if place_id else None,
                )
            if place_id:
                return {"status": "not_matched", "reason": "place_not_found", "attempted_at": attempted_at}
        decision = select_candidate(lead, _text_search(client, api_key, query))
    except httpx.HTTPError as exc:
        return {"status": "provider_error", "error": _error_summary(exc), "attempted_at": attempted_at}
    finally:
        if owns_client:
            client.close()
    if decision["status"] == "verified":
        result = _verified_result(
            decision["match"]["candidate"], method="text_search", assessment=decision["match"], attempted_at=attempted_at
        )
    else:
        result = {
            "status": decision["status"],
            "reason": decision["reason"],
            "attempted_at": attempted_at,
            "candidates": decision["candidates"],
        }
    result["query"] = query
    if known_id and not place_id:
        result["previous_place_id"] = known_id
    return result


def merge_place_result(lead: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Store a lookup on the lead without losing earlier verified data.

    `research.google_places` holds the last verified record (or, if there has
    never been one, the latest attempt); `last_attempt` always says what the
    latest lookup found.
    """
    row = dict(lead)
    research = dict(row.get("research") or {})
    previous = research.get("google_places") or {}
    attempt = {
        key: result.get(key)
        for key in ("status", "reason", "error", "attempted_at", "candidates", "match_method")
        if result.get(key) is not None
    }
    if result.get("status") != "verified":
        base = previous if previous.get("status") == "verified" else result
        research["google_places"] = {**base, "last_attempt": attempt}
        row["research"] = research
        return row
    research["google_places"] = {**result, "last_attempt": attempt}
    row["research"] = research
    row["maps_url"] = result.get("maps_url") or row.get("maps_url")
    row["address"] = result.get("formatted_address") or row.get("address")
    row["rating"] = result.get("rating") if result.get("rating") is not None else row.get("rating")
    row["review_count"] = result.get("review_count") if result.get("review_count") is not None else row.get("review_count")
    row["phone"] = row.get("phone") or result.get("phone")
    website = dict(row.get("website") or {})
    website["website_url"] = website.get("website_url") or result.get("website_url")
    row["website"] = website
    return row


def ambiguous_candidate_ids(lead: dict[str, Any]) -> set[str]:
    """Place ids a person may pick for this lead: the latest ambiguous
    candidates plus the place id the lead already has."""
    places = ((lead.get("research") or {}).get("google_places") or {})
    attempt = places.get("last_attempt") or places
    ids = {
        str(item.get("place_id"))
        for item in (attempt.get("candidates") or [])
        if item.get("place_id")
    }
    current = google_place_id(lead)
    if current:
        ids.add(current)
    return ids
