from __future__ import annotations

from urllib.parse import urlparse

from common import load_json
from growth_attribution import OBJECTIVES


def fail(message: str) -> None:
    raise SystemExit(f"growth configuration invalid: {message}")


def main() -> None:
    ecosystem = load_json("config/ecosystem.json")
    policy = load_json("config/growth-policy.json")
    channels = load_json("config/channel-taxonomy.json")

    if policy.get("schema_version") != 1:
        fail("growth-policy schema_version must be 1")
    if channels.get("schema_version") != 1:
        fail("channel-taxonomy schema_version must be 1")

    prefix = policy.get("campaign_id_prefix")
    if not isinstance(prefix, str) or not prefix.strip():
        fail("campaign_id_prefix is required")

    states = policy.get("allowed_states")
    if not isinstance(states, list) or len(states) != len(set(states)):
        fail("allowed_states must be a unique list")
    required_states = {"planned", "approved", "active", "measuring", "completed", "rejected", "archived"}
    if set(states) != required_states:
        fail("allowed_states does not match the required lifecycle")

    transitions = policy.get("state_transitions")
    if not isinstance(transitions, dict) or set(transitions) != required_states:
        fail("state_transitions must define every lifecycle state")
    for source, destinations in transitions.items():
        if not isinstance(destinations, list):
            fail(f"transitions for {source} must be a list")
        unknown = set(destinations) - required_states
        if unknown:
            fail(f"{source} transitions to unknown state(s): {sorted(unknown)}")

    utm = policy.get("utm", {})
    required_utm = {"utm_source", "utm_medium", "utm_campaign"}
    if set(utm.get("required_parameters", [])) != required_utm:
        fail("UTM required parameters must be source, medium and campaign")
    if int(utm.get("max_value_chars", 0)) < 32:
        fail("UTM max_value_chars is too small")

    performance = policy.get("performance", {})
    required_metrics = {
        "impressions", "clicks", "engaged_visits",
        "cta_actions", "leads", "conversions"
    }
    if set(performance.get("required_metrics", [])) != required_metrics:
        fail("required performance metrics do not match the contract")
    targets = performance.get("targets_pct", {})
    weights = performance.get("score_weights", {})
    expected_rates = {
        "ctr", "engaged_visit_rate", "cta_rate", "lead_rate", "conversion_rate"
    }
    if set(targets) != expected_rates or set(weights) != expected_rates:
        fail("targets_pct and score_weights must define every rate")
    if any(float(value) <= 0 for value in targets.values()):
        fail("all performance targets must be positive")
    total_weight = sum(float(value) for value in weights.values())
    if abs(total_weight - 1.0) > 1e-9:
        fail(f"score_weights must sum to 1.0, got {total_weight}")

    privacy = policy.get("privacy", {})
    if privacy.get("aggregate_only") is not True:
        fail("aggregate_only must be true")
    if not privacy.get("forbidden_fields"):
        fail("forbidden_fields cannot be empty")
    if not privacy.get("forbidden_key_substrings"):
        fail("forbidden_key_substrings cannot be empty")

    channel_items = channels.get("channels")
    if not isinstance(channel_items, list) or not channel_items:
        fail("channels must be a non-empty list")
    ids = [item.get("id") for item in channel_items]
    if None in ids or len(ids) != len(set(ids)):
        fail("channel IDs must be unique and non-empty")
    enabled = 0
    for item in channel_items:
        for key in ("id", "utm_source", "utm_medium", "enabled"):
            if key not in item:
                fail(f"channel {item.get('id', '?')} missing {key}")
        if not isinstance(item["enabled"], bool):
            fail(f"channel {item['id']} enabled must be boolean")
        if item["enabled"]:
            enabled += 1
        if not str(item["utm_source"]).strip() or not str(item["utm_medium"]).strip():
            fail(f"channel {item['id']} UTM values cannot be blank")
    if enabled < 3:
        fail("at least three distribution channels must be enabled")

    home = ecosystem.get("canonical_home", "")
    parsed = urlparse(home)
    if parsed.scheme != "https" or not parsed.hostname:
        fail("ecosystem canonical_home must be absolute HTTPS")

    platform_ids = [p.get("id") for p in ecosystem.get("platforms", [])]
    if not platform_ids or len(platform_ids) != len(set(platform_ids)):
        fail("ecosystem platform IDs must be unique and non-empty")

    if set(OBJECTIVES) != {"authority", "demand", "adoption", "launch", "education", "trust"}:
        fail("campaign objective contract unexpectedly changed")

    print(
        f"Growth configuration valid: {len(platform_ids)} platforms, "
        f"{len(channel_items)} channels, {enabled} enabled."
    )


if __name__ == "__main__":
    main()
