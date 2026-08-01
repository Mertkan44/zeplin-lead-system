from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

import httpx

from src.config import env


PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.googleMapsUri",
        "places.businessStatus",
        "places.nationalPhoneNumber",
        "places.rating",
        "places.userRatingCount",
        "places.websiteUri",
        "places.primaryType",
    ]
)


def is_configured() -> bool:
    return bool(env("GOOGLE_PLACES_API_KEY"))


def _normalized(value: Any) -> str:
    raw = unicodedata.normalize("NFKD", str(value or "").casefold())
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


def _location_similarity(lead: dict[str, Any], candidate: dict[str, Any]) -> float:
    expected = _normalized(" ".join([str(lead.get("city") or ""), str(lead.get("address") or "")]))
    actual = _normalized(candidate.get("formattedAddress"))
    if not expected or not actual:
        return 0.5
    expected_tokens = {token for token in expected.split() if len(token) > 2}
    if not expected_tokens:
        return 0.5
    hits = sum(1 for token in expected_tokens if token in actual)
    return min(1.0, hits / min(len(expected_tokens), 4))


def select_best_candidate(lead: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    ranked = []
    for candidate in candidates:
        display_name = (candidate.get("displayName") or {}).get("text") or ""
        name_score = _name_similarity(str(lead.get("name") or ""), display_name)
        location_score = _location_similarity(lead, candidate)
        confidence = round((name_score * 0.8 + location_score * 0.2) * 100)
        ranked.append((confidence, name_score, candidate))
    if not ranked:
        return None
    confidence, name_score, candidate = max(ranked, key=lambda item: item[0])
    if name_score < 0.72 or confidence < 72:
        return None
    return {**candidate, "matchConfidence": confidence}


def search_place(
    lead: dict[str, Any],
    *,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    api_key = env("GOOGLE_PLACES_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_PLACES_API_KEY is not configured")
    query_parts = [lead.get("name"), lead.get("address"), lead.get("city")]
    query = ", ".join(str(value).strip() for value in query_parts if value)
    payload = {
        "textQuery": query,
        "pageSize": 3,
        "languageCode": "tr",
        "regionCode": "TR",
    }
    owns_client = client is None
    client = client or httpx.Client(timeout=20)
    try:
        response = client.post(
            PLACES_TEXT_SEARCH_URL,
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": PLACES_FIELD_MASK,
            },
            json=payload,
        )
        response.raise_for_status()
        places = response.json().get("places") or []
    finally:
        if owns_client:
            client.close()
    match = select_best_candidate(lead, places)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    if not match:
        return {
            "status": "not_matched",
            "query": query,
            "refreshed_at": now,
            "candidate_count": len(places),
        }
    return {
        "status": "verified",
        "query": query,
        "refreshed_at": now,
        "place_id": match.get("id"),
        "display_name": (match.get("displayName") or {}).get("text"),
        "formatted_address": match.get("formattedAddress"),
        "maps_url": match.get("googleMapsUri"),
        "business_status": match.get("businessStatus"),
        "phone": match.get("nationalPhoneNumber"),
        "rating": match.get("rating"),
        "review_count": match.get("userRatingCount"),
        "website_url": match.get("websiteUri"),
        "primary_type": match.get("primaryType"),
        "match_confidence": match.get("matchConfidence"),
    }


def merge_place_result(lead: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    row = dict(lead)
    research = dict(row.get("research") or {})
    research["google_places"] = result
    row["research"] = research
    if result.get("status") != "verified":
        return row
    row["maps_url"] = result.get("maps_url") or row.get("maps_url")
    row["address"] = result.get("formatted_address") or row.get("address")
    row["rating"] = result.get("rating") if result.get("rating") is not None else row.get("rating")
    row["review_count"] = result.get("review_count") if result.get("review_count") is not None else row.get("review_count")
    row["phone"] = row.get("phone") or result.get("phone")
    website = dict(row.get("website") or {})
    website["website_url"] = website.get("website_url") or result.get("website_url")
    row["website"] = website
    return row
