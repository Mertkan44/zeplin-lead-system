from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


VALID_GRADES = {"A", "B", "C", "D"}
REQUIRED_TOP_LEVEL = {
    "name",
    "website",
    "social",
    "scoring",
    "matched_services",
    "recommended_package",
    "estimated_value_tl",
    "sales_priority_score",
    "next_action",
    "data_quality",
    "schema_version",
}
REQUIRED_WEBSITE = {
    "has_website",
    "website_url",
    "has_ssl",
    "is_mobile_friendly",
    "load_time_ms",
    "website_loads",
    "has_schema",
    "has_og",
    "has_email_capture",
    "has_whatsapp",
}
REQUIRED_SOCIAL = {"has_instagram", "instagram_url", "instagram_username", "stats", "tiktok"}
REQUIRED_SOCIAL_STATS = {
    "followers",
    "post_count",
    "avg_likes",
    "avg_comments",
    "engagement_rate",
}
REQUIRED_SCORING = {"score", "max_score", "grade", "issues", "opportunities"}
REQUIRED_DATA_QUALITY = {
    "has_contact",
    "has_maps_rating",
    "has_service_match",
    "has_ai",
    "has_audit_depth",
}


@dataclass(frozen=True)
class ValidationIssue:
    lead: str
    field: str
    message: str

    def format(self) -> str:
        return f"{self.lead}: {self.field} - {self.message}"


def _lead_name(lead: dict[str, Any], index: int) -> str:
    name = lead.get("name")
    return str(name) if name else f"lead[{index}]"


def _require_keys(
    issues: list[ValidationIssue],
    lead_name: str,
    field: str,
    value: Any,
    required: set[str],
) -> None:
    if not isinstance(value, dict):
        issues.append(ValidationIssue(lead_name, field, "must be an object"))
        return
    for key in sorted(required - set(value)):
        issues.append(ValidationIssue(lead_name, f"{field}.{key}", "is missing"))


def _check_number(
    issues: list[ValidationIssue],
    lead_name: str,
    field: str,
    value: Any,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        issues.append(ValidationIssue(lead_name, field, "must be numeric"))
        return
    if minimum is not None and value < minimum:
        issues.append(ValidationIssue(lead_name, field, f"must be >= {minimum}"))
    if maximum is not None and value > maximum:
        issues.append(ValidationIssue(lead_name, field, f"must be <= {maximum}"))


def _check_list(
    issues: list[ValidationIssue],
    lead_name: str,
    field: str,
    value: Any,
) -> None:
    if not isinstance(value, list):
        issues.append(ValidationIssue(lead_name, field, "must be a list"))


def validate_leads(leads: Any) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not isinstance(leads, list):
        return [ValidationIssue("payload", "root", "must be a list")]

    seen_names: set[str] = set()
    for index, lead in enumerate(leads):
        if not isinstance(lead, dict):
            issues.append(ValidationIssue(f"lead[{index}]", "root", "must be an object"))
            continue

        lead_name = _lead_name(lead, index)
        missing = REQUIRED_TOP_LEVEL - set(lead)
        for key in sorted(missing):
            issues.append(ValidationIssue(lead_name, key, "is missing"))

        name = lead.get("name")
        if not isinstance(name, str) or not name.strip():
            issues.append(ValidationIssue(lead_name, "name", "must be a non-empty string"))
        elif name in seen_names:
            issues.append(ValidationIssue(lead_name, "name", "duplicates another lead"))
        else:
            seen_names.add(name)

        schema_version = lead.get("schema_version")
        if schema_version is not None:
            _check_number(issues, lead_name, "schema_version", schema_version, minimum=2)

        _check_number(issues, lead_name, "estimated_value_tl", lead.get("estimated_value_tl"), minimum=0)
        _check_number(
            issues,
            lead_name,
            "sales_priority_score",
            lead.get("sales_priority_score"),
            minimum=0,
            maximum=100,
        )

        if not isinstance(lead.get("next_action"), str) or not lead.get("next_action"):
            issues.append(ValidationIssue(lead_name, "next_action", "must be a non-empty string"))

        website = lead.get("website")
        _require_keys(issues, lead_name, "website", website, REQUIRED_WEBSITE)

        social = lead.get("social")
        _require_keys(issues, lead_name, "social", social, REQUIRED_SOCIAL)
        if isinstance(social, dict):
            _require_keys(issues, lead_name, "social.stats", social.get("stats"), REQUIRED_SOCIAL_STATS)
            _require_keys(
                issues,
                lead_name,
                "social.tiktok",
                social.get("tiktok"),
                {"has_tiktok", "tiktok_url", "tiktok_username"},
            )

        scoring = lead.get("scoring")
        _require_keys(issues, lead_name, "scoring", scoring, REQUIRED_SCORING)
        if isinstance(scoring, dict):
            _check_number(issues, lead_name, "scoring.score", scoring.get("score"), minimum=0, maximum=100)
            _check_number(issues, lead_name, "scoring.max_score", scoring.get("max_score"), minimum=1)
            if scoring.get("grade") not in VALID_GRADES:
                issues.append(ValidationIssue(lead_name, "scoring.grade", "must be A, B, C, or D"))
            _check_list(issues, lead_name, "scoring.issues", scoring.get("issues"))
            _check_list(issues, lead_name, "scoring.opportunities", scoring.get("opportunities"))

        matched_services = lead.get("matched_services")
        _check_list(issues, lead_name, "matched_services", matched_services)
        if isinstance(matched_services, list):
            for svc_index, service in enumerate(matched_services):
                if not isinstance(service, dict):
                    issues.append(
                        ValidationIssue(lead_name, f"matched_services[{svc_index}]", "must be an object")
                    )
                    continue
                for key in ("slug", "name", "owner", "price_min", "price_max", "monthly"):
                    if key not in service:
                        issues.append(
                            ValidationIssue(lead_name, f"matched_services[{svc_index}].{key}", "is missing")
                        )

        package = lead.get("recommended_package")
        _require_keys(
            issues,
            lead_name,
            "recommended_package",
            package,
            {"name", "included_services", "owner", "stage", "confidence", "evidence"},
        )
        if isinstance(package, dict):
            _check_list(issues, lead_name, "recommended_package.included_services", package.get("included_services"))
            _check_list(issues, lead_name, "recommended_package.evidence", package.get("evidence"))
            _check_number(
                issues,
                lead_name,
                "recommended_package.confidence",
                package.get("confidence"),
                minimum=0,
                maximum=100,
            )

        data_quality = lead.get("data_quality")
        _require_keys(issues, lead_name, "data_quality", data_quality, REQUIRED_DATA_QUALITY)
        if isinstance(data_quality, dict):
            for key in REQUIRED_DATA_QUALITY:
                if key in data_quality and not isinstance(data_quality[key], bool):
                    issues.append(ValidationIssue(lead_name, f"data_quality.{key}", "must be boolean"))

    return issues


def format_issues(issues: list[ValidationIssue], *, limit: int | None = None) -> str:
    visible = issues[:limit] if limit else issues
    lines = [issue.format() for issue in visible]
    if limit and len(issues) > limit:
        lines.append(f"...and {len(issues) - limit} more")
    return "\n".join(lines)


def load_json(path: Path) -> Any:
    import json

    return json.loads(path.read_text(encoding="utf-8"))
