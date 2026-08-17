from __future__ import annotations

from common import load_json
from growth_attribution import OBJECTIVES


def fail(message: str) -> None:
    raise SystemExit(f"editorial configuration invalid: {message}")


def _positive_int(policy: dict, key: str, *, minimum: int = 1) -> int:
    value = policy.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        fail(f"{key} must be an integer >= {minimum}")
    return value


def main() -> None:
    ecosystem = load_json("config/ecosystem.json")
    policy = load_json("config/editorial-policy.json")

    if policy.get("schema_version") != 1:
        fail("schema_version must be 1")

    history_days = _positive_int(policy, "history_lookback_days", minimum=7)
    coverage_days = _positive_int(policy, "coverage_window_days", minimum=7)
    objective_days = _positive_int(policy, "objective_lookback_days", minimum=7)
    max_week = _positive_int(policy, "max_campaigns_per_iso_week")
    rolling_days = _positive_int(policy, "max_campaigns_rolling_window_days")
    max_rolling = _positive_int(policy, "max_campaigns_in_rolling_window")
    min_spacing = _positive_int(policy, "minimum_days_between_campaigns")
    platform_cooldown = _positive_int(policy, "minimum_days_between_same_platform")
    max_platform = _positive_int(policy, "max_campaigns_per_platform_in_lookback")
    coverage_target = _positive_int(policy, "coverage_target_per_platform")
    objective_cap = _positive_int(policy, "max_same_objective_in_lookback")

    if coverage_days > history_days:
        fail("coverage_window_days cannot exceed history_lookback_days")
    if objective_days > history_days:
        fail("objective_lookback_days cannot exceed history_lookback_days")
    if rolling_days > history_days:
        fail("max_campaigns_rolling_window_days cannot exceed history_lookback_days")
    if min_spacing >= rolling_days:
        fail("minimum_days_between_campaigns must be smaller than rolling window")
    if platform_cooldown >= history_days:
        fail("minimum_days_between_same_platform must be smaller than history lookback")
    if max_rolling > max_week + 1:
        fail("rolling capacity is unexpectedly looser than ISO-week capacity")
    if coverage_target > max_platform:
        fail("coverage_target_per_platform cannot exceed per-platform lookback cap")
    if objective_cap > max_rolling * 3:
        fail("objective cap is too loose relative to rolling campaign capacity")

    for key in (
        "all_platform_campaign_touches_every_platform",
        "allow_manual_all_platform_campaign",
        "manual_requests_respect_objective_cap",
    ):
        if not isinstance(policy.get(key), bool):
            fail(f"{key} must be boolean")

    platform_ids = [item.get("id") for item in ecosystem.get("platforms", [])]
    if not platform_ids or None in platform_ids or len(platform_ids) != len(set(platform_ids)):
        fail("ecosystem platform IDs must be unique and non-empty")
    platform_set = set(platform_ids)

    platform_priorities = policy.get("platform_priorities")
    if not isinstance(platform_priorities, dict) or set(platform_priorities) != platform_set:
        fail("platform_priorities must define every ecosystem platform exactly once")
    for platform_id, value in platform_priorities.items():
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 10:
            fail(f"platform priority for {platform_id} must be integer 1..10")

    objective_set = set(OBJECTIVES)
    objective_priorities = policy.get("objective_priorities")
    if not isinstance(objective_priorities, dict) or set(objective_priorities) != objective_set:
        fail("objective_priorities must define every campaign objective exactly once")
    for objective, value in objective_priorities.items():
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 10:
            fail(f"objective priority for {objective} must be integer 1..10")

    platform_objectives = policy.get("platform_objectives")
    if not isinstance(platform_objectives, dict) or set(platform_objectives) != platform_set:
        fail("platform_objectives must define every ecosystem platform exactly once")
    for platform_id, objectives in platform_objectives.items():
        if not isinstance(objectives, list) or not objectives:
            fail(f"platform {platform_id} requires at least one approved objective")
        if len(objectives) != len(set(objectives)):
            fail(f"platform {platform_id} contains duplicate objectives")
        unknown = set(objectives) - objective_set
        if unknown:
            fail(f"platform {platform_id} contains unknown objectives: {sorted(unknown)}")

    if max_week > len(platform_set):
        fail("weekly capacity cannot exceed the number of governed platforms")

    print(
        "Editorial configuration valid: "
        f"{len(platform_set)} platforms, {len(objective_set)} objectives, "
        f"weekly capacity {max_week}, rolling capacity {max_rolling}/{rolling_days}d."
    )


if __name__ == "__main__":
    main()
