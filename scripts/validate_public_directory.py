from __future__ import annotations

import json
from urllib.parse import urlparse

from claims_governance import find_sensitive_identifiers, load_policy as load_claims_policy
from common import load_json


SECTIONS_WITH_URLS = (
    "platforms",
    "public_endpoints",
    "channels",
    "publications",
    "public_repositories",
)

FORBIDDEN_PUBLIC_KEYS = {
    "pan",
    "gstin",
    "udyam",
    "razorpay",
    "plan_id",
    "secret",
    "token",
    "password",
    "api_key",
}


def _walk_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield str(key).lower()
            yield from _walk_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_keys(nested)


def validate() -> list[str]:
    data = load_json("config/public-directory.json")
    errors: list[str] = []

    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if data.get("brand") != "CYBERDUDEBIVASH®":
        errors.append("brand must be CYBERDUDEBIVASH®")

    canonical_home = data.get("canonical_home", "")
    parsed_home = urlparse(canonical_home)
    if parsed_home.scheme != "https" or not parsed_home.netloc:
        errors.append("canonical_home must be a valid HTTPS URL")

    contact = data.get("public_contact", {})
    if not contact.get("emails"):
        errors.append("public_contact requires at least one email")
    if not contact.get("phone"):
        errors.append("public_contact requires a phone")

    for section_name in SECTIONS_WITH_URLS:
        section = data.get(section_name)
        if not isinstance(section, list) or not section:
            errors.append(f"{section_name} must be a non-empty list")
            continue

        seen_ids: set[str] = set()
        seen_urls: set[str] = set()
        for index, item in enumerate(section):
            item_id = item.get("id")
            url = item.get("url")
            if not item_id:
                errors.append(f"{section_name}[{index}] requires id")
            elif item_id in seen_ids:
                errors.append(f"duplicate id in {section_name}: {item_id}")
            else:
                seen_ids.add(item_id)

            if not url:
                errors.append(f"{section_name}[{index}] requires url")
                continue
            parsed = urlparse(url)
            if parsed.scheme != "https" or not parsed.netloc:
                errors.append(f"invalid HTTPS URL in {section_name}: {url}")
            if url in seen_urls:
                errors.append(f"duplicate URL in {section_name}: {url}")
            seen_urls.add(url)

    keys = set(_walk_keys(data))
    forbidden = sorted(key for key in keys if key in FORBIDDEN_PUBLIC_KEYS)
    if forbidden:
        errors.append(
            "public directory contains forbidden sensitive/internal keys: "
            + ", ".join(forbidden)
        )

    claims_policy = load_claims_policy()
    sensitive_values = find_sensitive_identifiers(
        json.dumps(data, ensure_ascii=False),
        claims_policy,
    )
    if sensitive_values:
        errors.append(
            "public directory contains forbidden sensitive identifier values: "
            + ", ".join(sensitive_values)
        )

    return errors


if __name__ == "__main__":
    failures = validate()
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        raise SystemExit(1)
    print("Public directory validation passed.")
