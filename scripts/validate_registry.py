from __future__ import annotations

from urllib.parse import urlparse
from common import load_json


def validate() -> list[str]:
    data = load_json("config/ecosystem.json")
    errors: list[str] = []
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()

    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if data.get("brand") != "CYBERDUDEBIVASH®":
        errors.append("brand must be CYBERDUDEBIVASH®")

    platforms = data.get("platforms")
    if not isinstance(platforms, list) or not platforms:
        errors.append("platforms must be a non-empty list")
        return errors

    required = {"id", "name", "url", "category", "audiences", "positioning"}
    for index, item in enumerate(platforms):
        missing = required - item.keys()
        if missing:
            errors.append(f"platform[{index}] missing: {', '.join(sorted(missing))}")
            continue
        if item["id"] in seen_ids:
            errors.append(f"duplicate id: {item['id']}")
        seen_ids.add(item["id"])
        if item["url"] in seen_urls:
            errors.append(f"duplicate url: {item['url']}")
        seen_urls.add(item["url"])
        parsed = urlparse(item["url"])
        if parsed.scheme != "https" or not parsed.netloc:
            errors.append(f"invalid HTTPS URL: {item['url']}")
        if not item["audiences"]:
            errors.append(f"{item['id']} requires at least one audience")
        if "CYBERDUDEBIVASH" not in item["name"]:
            errors.append(f"{item['id']} name must preserve brand identity")

    return errors


if __name__ == "__main__":
    failures = validate()
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        raise SystemExit(1)
    print("Registry validation passed.")
