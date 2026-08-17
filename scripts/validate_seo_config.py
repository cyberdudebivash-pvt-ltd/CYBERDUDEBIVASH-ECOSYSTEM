from __future__ import annotations

import json

from common import ROOT, load_json
from seo_opportunity import validate_registry


class ConfigError(ValueError):
    pass


def _sum_is_one(values: dict[str, float]) -> bool:
    return abs(sum(float(v) for v in values.values()) - 1.0) < 1e-9


def validate() -> None:
    policy = load_json("config/seo-policy.json")
    registry = load_json("config/seo-topics.json")
    ecosystem = load_json("config/ecosystem.json")
    if policy.get("schema_version") != 1:
        raise ConfigError("SEO policy schema_version must be 1")
    if not _sum_is_one(policy.get("internal_weights", {})):
        raise ConfigError("SEO internal_weights must sum to 1")
    if not _sum_is_one(policy.get("external_weights", {})):
        raise ConfigError("SEO external_weights must sum to 1")
    if not _sum_is_one(policy.get("blend", {})):
        raise ConfigError("SEO blend weights must sum to 1")
    if not 0 <= float(policy.get("recommendation_threshold", -1)) <= 100:
        raise ConfigError("SEO recommendation_threshold must be 0..100")
    if int(policy.get("max_report_items", 0)) <= 0:
        raise ConfigError("SEO max_report_items must be positive")
    if not policy.get("approved_external_providers"):
        raise ConfigError("approved_external_providers cannot be empty")
    validate_registry(registry, policy, ecosystem)

    schema = json.loads((ROOT / "schemas/seo-opportunity.schema.json").read_text(encoding="utf-8"))
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise ConfigError("SEO schema must use JSON Schema 2020-12")
    if schema.get("title") != "CYBERDUDEBIVASH SEO Opportunity":
        raise ConfigError("unexpected SEO schema title")

    print(f"SEO policy and {len(registry['topics'])} governed topic(s) validated")


if __name__ == "__main__":
    validate()
