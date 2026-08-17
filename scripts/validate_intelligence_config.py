from __future__ import annotations

from urllib.parse import urlparse

from common import load_json

ALLOWED_SOURCE_TYPES = {"json", "github-releases"}
ALLOWED_PURPOSES = {
    "threat-intelligence",
    "ai-security-intelligence",
    "research",
    "product-release",
}


def validate() -> list[str]:
    errors: list[str] = []
    sources_cfg = load_json("config/intelligence-sources.json")
    policy = load_json("config/intelligence-policy.json")
    ecosystem = load_json("config/ecosystem.json")

    if sources_cfg.get("schema_version") != 1:
        errors.append("intelligence-sources schema_version must be 1")
    if policy.get("schema_version") != 1:
        errors.append("intelligence-policy schema_version must be 1")

    platform_ids = {item["id"] for item in ecosystem.get("platforms", [])}
    allowed_hosts = set(sources_cfg.get("allowed_hosts", []))
    if not allowed_hosts:
        errors.append("allowed_hosts must be non-empty")

    required_source_keys = {"id", "type", "platform", "purpose", "trust_level", "enabled"}
    seen_ids: set[str] = set()

    for index, source in enumerate(sources_cfg.get("sources", [])):
        missing = required_source_keys - source.keys()
        if missing:
            errors.append(f"source[{index}] missing: {', '.join(sorted(missing))}")
            continue
        source_id = source["id"]
        if source_id in seen_ids:
            errors.append(f"duplicate source id: {source_id}")
        seen_ids.add(source_id)
        if source["type"] not in ALLOWED_SOURCE_TYPES:
            errors.append(f"{source_id}: unsupported source type {source['type']}")
        if source["platform"] not in platform_ids:
            errors.append(f"{source_id}: unknown platform {source['platform']}")
        if source["purpose"] not in ALLOWED_PURPOSES:
            errors.append(f"{source_id}: unsupported purpose {source['purpose']}")
        trust = source["trust_level"]
        if not isinstance(trust, int) or not 1 <= trust <= 5:
            errors.append(f"{source_id}: trust_level must be integer 1..5")

        if source["type"] == "json":
            url = source.get("url", "")
            parsed = urlparse(url)
            if parsed.scheme != "https" or not parsed.hostname:
                errors.append(f"{source_id}: JSON source requires valid HTTPS URL")
            elif parsed.hostname not in allowed_hosts:
                errors.append(f"{source_id}: host not allowlisted: {parsed.hostname}")
        elif source["type"] == "github-releases":
            repository = source.get("repository", "")
            if not repository.startswith("cyberdudebivash-pvt-ltd/"):
                errors.append(f"{source_id}: GitHub source must use approved organization repository")

    if not sources_cfg.get("sources"):
        errors.append("sources must be a non-empty list")

    numeric_rules = {
        "minimum_evidence_score": (1, 5),
        "minimum_total_score": (1, 30),
        "max_signal_age_days": (1, 365),
        "max_items_per_source": (1, 100),
        "max_issues_per_run": (1, 20),
        "request_timeout_seconds": (1, 60),
        "max_response_bytes": (1024, 10_000_000),
        "max_title_chars": (40, 500),
        "max_summary_chars": (100, 5000),
    }
    for key, (minimum, maximum) in numeric_rules.items():
        value = policy.get(key)
        if not isinstance(value, int) or not minimum <= value <= maximum:
            errors.append(f"policy {key} must be integer in range {minimum}..{maximum}")

    if isinstance(policy.get("minimum_evidence_score"), int) and policy["minimum_evidence_score"] < 3:
        errors.append("minimum_evidence_score must remain >= 3 for evidence gating")
    if isinstance(policy.get("minimum_total_score"), int) and policy["minimum_total_score"] < 15:
        errors.append("minimum_total_score must remain >= 15 to suppress low-signal noise")

    return errors


if __name__ == "__main__":
    failures = validate()
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        raise SystemExit(1)
    print("Campaign intelligence configuration validation passed.")
