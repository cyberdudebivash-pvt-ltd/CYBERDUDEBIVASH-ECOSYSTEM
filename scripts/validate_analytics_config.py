from __future__ import annotations

import json

from common import ROOT, load_json


class ConfigError(ValueError):
    pass


def validate() -> None:
    policy = load_json("config/analytics-policy.json")
    if policy.get("schema_version") != 1:
        raise ConfigError("analytics policy schema_version must be 1")
    if policy.get("runtime_boundary") != "private-only":
        raise ConfigError("analytics runtime boundary must remain private-only")
    if policy.get("public_repository_runtime_inputs_forbidden") is not True:
        raise ConfigError("public repository analytics runtime inputs must be forbidden")
    if int(policy.get("retention_days", 0)) <= 0:
        raise ConfigError("retention_days must be positive")
    if not 1 <= int(policy.get("max_batch_records", 0)) <= 100000:
        raise ConfigError("max_batch_records out of bounds")

    providers = policy.get("providers")
    if not isinstance(providers, list) or not providers:
        raise ConfigError("analytics providers required")
    ids = [item.get("id") for item in providers]
    if len(ids) != len(set(ids)):
        raise ConfigError("duplicate analytics provider")
    if not any(item.get("enabled") for item in providers):
        raise ConfigError("at least one analytics provider must be enabled")
    for item in providers:
        if item.get("mode") not in {"file", "api"}:
            raise ConfigError(f"invalid provider mode for {item.get('id')}")

    record_types = policy.get("record_types", {})
    if set(record_types) != {"funnel", "assist"}:
        raise ConfigError("analytics record_types must be funnel and assist")
    for name, cfg in record_types.items():
        metrics = cfg.get("required_metrics")
        if not isinstance(metrics, list) or not metrics or len(metrics) != len(set(metrics)):
            raise ConfigError(f"{name} metrics must be a unique non-empty list")

    privacy = policy.get("privacy", {})
    if privacy.get("aggregate_only") is not True:
        raise ConfigError("analytics privacy must be aggregate_only")
    if not privacy.get("forbidden_fields") or not privacy.get("forbidden_key_substrings"):
        raise ConfigError("analytics privacy denylist cannot be empty")
    if int(privacy.get("max_landing_path_chars", 0)) <= 0:
        raise ConfigError("max_landing_path_chars must be positive")

    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    required_ignores = {"private/", "reports/private-analytics-*"}
    missing = [item for item in required_ignores if item not in gitignore]
    if missing:
        raise ConfigError("missing private analytics gitignore rule(s): " + ", ".join(missing))

    schema = json.loads((ROOT / "schemas/analytics-aggregate.schema.json").read_text(encoding="utf-8"))
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise ConfigError("analytics schema must use JSON Schema 2020-12")
    if schema.get("title") != "CYBERDUDEBIVASH Private Aggregate Analytics":
        raise ConfigError("unexpected analytics schema title")

    print("Analytics policy and private-runtime boundary validated")


if __name__ == "__main__":
    validate()
