from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from common import ROOT, load_json
from growth_attribution import OBJECTIVES


CAMPAIGN_TITLE_PREFIX = "Global Campaign:"
CAMPAIGN_TITLE_RE = re.compile(
    r"^Global Campaign:\s+(.+?)\s+/\s+([a-z-]+)\s+/\s+([a-z0-9-]+)\s*$"
)
AUTO = "auto"


class PlanningError(ValueError):
    """Raised when planning inputs are structurally unsafe or ambiguous."""


def _utc_date(value: str) -> dt.date:
    raw = str(value).strip()
    if not raw:
        raise PlanningError("history record date is blank")
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        try:
            return dt.date.fromisoformat(raw)
        except ValueError:
            raise PlanningError(f"invalid history date: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).date()


def _parse_history_item(item: dict[str, Any], *, as_of: dt.date) -> dict[str, Any] | None:
    title = str(item.get("title", "")).strip()
    if title and not title.startswith(CAMPAIGN_TITLE_PREFIX):
        return None

    # Tests and offline operators may provide normalized records directly.
    if not title and {"platform", "objective"}.issubset(item):
        campaign_date = item.get("campaign_date") or item.get("createdAt")
        if not campaign_date:
            raise PlanningError("normalized history record requires campaign_date or createdAt")
        date_value = _utc_date(str(campaign_date))
        if date_value > as_of:
            raise PlanningError(f"history record is in the future: {date_value}")
        return {
            "campaign_id": str(item.get("campaign_id", "normalized-history")).strip(),
            "platform": str(item["platform"]).strip(),
            "objective": str(item["objective"]).strip(),
            "date": date_value,
        }

    if not title:
        return None

    match = CAMPAIGN_TITLE_RE.fullmatch(title)
    if not match:
        raise PlanningError(
            "campaign history title uses the reserved prefix but does not match the governed format: "
            f"{title!r}"
        )
    campaign_id, objective, platform = match.groups()
    created_at = item.get("createdAt") or item.get("created_at")
    if not created_at:
        raise PlanningError(f"campaign history item {campaign_id!r} is missing createdAt")
    date_value = _utc_date(str(created_at))
    if date_value > as_of:
        raise PlanningError(f"campaign {campaign_id!r} is dated in the future: {date_value}")
    return {
        "campaign_id": campaign_id.strip(),
        "platform": platform,
        "objective": objective,
        "date": date_value,
    }


def normalize_history(
    raw_history: Any,
    *,
    as_of: dt.date,
    platform_ids: set[str],
    objective_ids: set[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    if raw_history is None:
        return [], []
    if not isinstance(raw_history, list):
        raise PlanningError("campaign history must be a JSON array")

    normalized: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, raw in enumerate(raw_history):
        if not isinstance(raw, dict):
            raise PlanningError(f"campaign history item {index} must be an object")
        item = _parse_history_item(raw, as_of=as_of)
        if item is None:
            continue
        if item["platform"] != "all" and item["platform"] not in platform_ids:
            warnings.append(
                f"ignored legacy/unknown platform {item['platform']!r} for balance scoring "
                f"from campaign {item['campaign_id']!r}"
            )
        if item["objective"] not in objective_ids:
            warnings.append(
                f"ignored legacy/unknown objective {item['objective']!r} for objective scoring "
                f"from campaign {item['campaign_id']!r}"
            )
        normalized.append(item)

    normalized.sort(key=lambda item: (item["date"], item["campaign_id"]))
    return normalized, warnings


def _window_start(as_of: dt.date, days: int) -> dt.date:
    return as_of - dt.timedelta(days=days - 1)


def _within(date_value: dt.date, *, as_of: dt.date, days: int) -> bool:
    return _window_start(as_of, days) <= date_value <= as_of


def _campaign_touches_platform(
    campaign_platform: str,
    target_platform: str,
    *,
    all_touches_every_platform: bool,
) -> bool:
    return campaign_platform == target_platform or (
        all_touches_every_platform and campaign_platform == "all"
    )


def _capacity_state(
    history: list[dict[str, Any]],
    policy: dict[str, Any],
    *,
    as_of: dt.date,
) -> dict[str, Any]:
    iso_year, iso_week, _ = as_of.isocalendar()
    same_week = [
        item
        for item in history
        if item["date"].isocalendar()[:2] == (iso_year, iso_week)
    ]
    rolling_days = int(policy["max_campaigns_rolling_window_days"])
    rolling = [
        item for item in history if _within(item["date"], as_of=as_of, days=rolling_days)
    ]
    last_date = max((item["date"] for item in history), default=None)
    days_since_last = None if last_date is None else (as_of - last_date).days

    return {
        "iso_year": iso_year,
        "iso_week": iso_week,
        "used_this_iso_week": len(same_week),
        "max_per_iso_week": int(policy["max_campaigns_per_iso_week"]),
        "used_in_rolling_window": len(rolling),
        "rolling_window_days": rolling_days,
        "max_in_rolling_window": int(policy["max_campaigns_in_rolling_window"]),
        "last_campaign_date": last_date.isoformat() if last_date else None,
        "days_since_last_campaign": days_since_last,
        "minimum_days_between_campaigns": int(policy["minimum_days_between_campaigns"]),
    }


def _capacity_block_reason(capacity: dict[str, Any]) -> str | None:
    if capacity["used_this_iso_week"] >= capacity["max_per_iso_week"]:
        return (
            "ISO-week campaign capacity exhausted "
            f"({capacity['used_this_iso_week']}/{capacity['max_per_iso_week']})"
        )
    if capacity["used_in_rolling_window"] >= capacity["max_in_rolling_window"]:
        return (
            "rolling campaign capacity exhausted "
            f"({capacity['used_in_rolling_window']}/{capacity['max_in_rolling_window']} "
            f"in {capacity['rolling_window_days']} days)"
        )
    days_since = capacity["days_since_last_campaign"]
    if (
        days_since is not None
        and days_since < capacity["minimum_days_between_campaigns"]
    ):
        return (
            "global campaign spacing not satisfied "
            f"({days_since}d since last; minimum "
            f"{capacity['minimum_days_between_campaigns']}d)"
        )
    return None


def _platform_candidates(
    history: list[dict[str, Any]],
    ecosystem: dict[str, Any],
    policy: dict[str, Any],
    *,
    as_of: dt.date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    lookback_days = int(policy["history_lookback_days"])
    coverage_days = int(policy["coverage_window_days"])
    cooldown_days = int(policy["minimum_days_between_same_platform"])
    max_in_lookback = int(policy["max_campaigns_per_platform_in_lookback"])
    coverage_target = int(policy["coverage_target_per_platform"])
    all_touches = bool(policy["all_platform_campaign_touches_every_platform"])
    priorities = policy["platform_priorities"]

    candidates: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for platform in ecosystem["platforms"]:
        platform_id = platform["id"]
        touches = [
            item
            for item in history
            if _campaign_touches_platform(
                item["platform"],
                platform_id,
                all_touches_every_platform=all_touches,
            )
        ]
        lookback = [
            item for item in touches if _within(item["date"], as_of=as_of, days=lookback_days)
        ]
        coverage = [
            item for item in touches if _within(item["date"], as_of=as_of, days=coverage_days)
        ]
        last_date = max((item["date"] for item in touches), default=None)
        days_since = None if last_date is None else (as_of - last_date).days
        coverage_debt = max(0, coverage_target - len(coverage))
        priority = int(priorities[platform_id])

        entry = {
            "platform": platform_id,
            "lookback_campaigns": len(lookback),
            "coverage_window_campaigns": len(coverage),
            "coverage_debt": coverage_debt,
            "last_campaign_date": last_date.isoformat() if last_date else None,
            "days_since_last_campaign": days_since,
            "strategic_priority": priority,
        }

        reasons: list[str] = []
        if days_since is not None and days_since < cooldown_days:
            reasons.append(
                f"platform cooldown active: {days_since}d since last; minimum {cooldown_days}d"
            )
        if len(lookback) >= max_in_lookback:
            reasons.append(
                f"platform lookback cap reached: {len(lookback)}/{max_in_lookback} "
                f"in {lookback_days} days"
            )
        if reasons:
            excluded.append({**entry, "reasons": reasons})
            continue

        # Deterministic lexicographic rank:
        # 1) coverage debt DESC, 2) recent count ASC,
        # 3) days since last DESC, 4) priority DESC, 5) platform ID ASC.
        days_rank = days_since if days_since is not None else lookback_days + coverage_days + 3650
        entry["rank_key"] = [
            -coverage_debt,
            len(lookback),
            -days_rank,
            -priority,
            platform_id,
        ]
        candidates.append(entry)

    candidates.sort(key=lambda item: tuple(item["rank_key"]))
    excluded.sort(key=lambda item: item["platform"])
    return candidates, excluded


def _objective_candidates(
    history: list[dict[str, Any]],
    policy: dict[str, Any],
    *,
    platform_id: str,
    as_of: dt.date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    allowed = list(policy["platform_objectives"][platform_id])
    lookback_days = int(policy["objective_lookback_days"])
    objective_cap = int(policy["max_same_objective_in_lookback"])
    priorities = policy["objective_priorities"]
    recent = [
        item
        for item in history
        if item["objective"] in OBJECTIVES
        and _within(item["date"], as_of=as_of, days=lookback_days)
    ]
    last_objective = recent[-1]["objective"] if recent else None

    candidates: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for objective in allowed:
        count = sum(1 for item in recent if item["objective"] == objective)
        repeat_last = objective == last_objective
        entry = {
            "objective": objective,
            "lookback_campaigns": count,
            "repeats_most_recent_objective": repeat_last,
            "strategic_priority": int(priorities[objective]),
        }
        if count >= objective_cap:
            excluded.append(
                {
                    **entry,
                    "reasons": [
                        f"objective lookback cap reached: {count}/{objective_cap} "
                        f"in {lookback_days} days"
                    ],
                }
            )
            continue

        # Deterministic rank:
        # 1) recent count ASC, 2) avoid immediate repeat,
        # 3) priority DESC, 4) objective ID ASC.
        entry["rank_key"] = [
            count,
            1 if repeat_last else 0,
            -int(priorities[objective]),
            objective,
        ]
        candidates.append(entry)

    candidates.sort(key=lambda item: tuple(item["rank_key"]))
    excluded.sort(key=lambda item: item["objective"])
    return candidates, excluded


def build_campaign_plan(
    ecosystem: dict[str, Any],
    policy: dict[str, Any],
    raw_history: Any,
    *,
    as_of: dt.date,
    requested_platform: str = AUTO,
    requested_objective: str = AUTO,
) -> dict[str, Any]:
    platform_ids = {item["id"] for item in ecosystem["platforms"]}
    objective_ids = set(OBJECTIVES)
    history, history_warnings = normalize_history(
        raw_history,
        as_of=as_of,
        platform_ids=platform_ids,
        objective_ids=objective_ids,
    )
    capacity = _capacity_state(history, policy, as_of=as_of)
    capacity_reason = _capacity_block_reason(capacity)
    base = {
        "schema_version": 1,
        "as_of": as_of.isoformat(),
        "status": None,
        "platform": None,
        "objective": None,
        "requested_platform": requested_platform,
        "requested_objective": requested_objective,
        "capacity": capacity,
        "history_records": len(history),
        "history_warnings": history_warnings,
        "reasons": [],
        "platform_candidates": [],
        "excluded_platforms": [],
        "objective_candidates": [],
        "excluded_objectives": [],
    }

    if capacity_reason:
        return {
            **base,
            "status": "capacity-exhausted",
            "reasons": [capacity_reason],
        }

    candidates, excluded = _platform_candidates(
        history, ecosystem, policy, as_of=as_of
    )
    base["platform_candidates"] = candidates
    base["excluded_platforms"] = excluded

    requested_platform = str(requested_platform or AUTO).strip()
    if requested_platform == "all":
        if policy.get("allow_manual_all_platform_campaign") is not True:
            return {
                **base,
                "status": "blocked",
                "reasons": ["manual all-platform campaigns are disabled by editorial policy"],
            }
        selected_platform = "all"
    elif requested_platform != AUTO:
        if requested_platform not in platform_ids:
            raise PlanningError(f"unknown requested platform: {requested_platform}")
        eligible_ids = {item["platform"] for item in candidates}
        if requested_platform not in eligible_ids:
            reasons = next(
                (
                    item["reasons"]
                    for item in excluded
                    if item["platform"] == requested_platform
                ),
                ["requested platform is not eligible"],
            )
            return {
                **base,
                "status": "blocked",
                "reasons": [
                    f"requested platform {requested_platform!r} is blocked: "
                    + "; ".join(reasons)
                ],
            }
        selected_platform = requested_platform
    else:
        if not candidates:
            return {
                **base,
                "status": "no-eligible-platform",
                "reasons": ["no platform satisfies the current cooldown and lookback caps"],
            }
        selected_platform = candidates[0]["platform"]

    if selected_platform == "all":
        allowed_objectives = sorted(OBJECTIVES)
        objective_policy = {**policy, "platform_objectives": {"all": allowed_objectives}}
        objective_candidates, excluded_objectives = _objective_candidates(
            history, objective_policy, platform_id="all", as_of=as_of
        )
    else:
        objective_candidates, excluded_objectives = _objective_candidates(
            history, policy, platform_id=selected_platform, as_of=as_of
        )
    base["objective_candidates"] = objective_candidates
    base["excluded_objectives"] = excluded_objectives

    requested_objective = str(requested_objective or AUTO).strip()
    if requested_objective != AUTO:
        if requested_objective not in objective_ids:
            raise PlanningError(f"unknown requested objective: {requested_objective}")
        allowed_for_platform = (
            set(OBJECTIVES)
            if selected_platform == "all"
            else set(policy["platform_objectives"][selected_platform])
        )
        if requested_objective not in allowed_for_platform:
            return {
                **base,
                "status": "blocked",
                "platform": selected_platform,
                "reasons": [
                    f"requested objective {requested_objective!r} is not approved for "
                    f"platform {selected_platform!r}"
                ],
            }
        eligible_objectives = {item["objective"] for item in objective_candidates}
        if (
            policy.get("manual_requests_respect_objective_cap") is True
            and requested_objective not in eligible_objectives
        ):
            reasons = next(
                (
                    item["reasons"]
                    for item in excluded_objectives
                    if item["objective"] == requested_objective
                ),
                ["requested objective is not eligible"],
            )
            return {
                **base,
                "status": "blocked",
                "platform": selected_platform,
                "reasons": [
                    f"requested objective {requested_objective!r} is blocked: "
                    + "; ".join(reasons)
                ],
            }
        selected_objective = requested_objective
    else:
        if not objective_candidates:
            return {
                **base,
                "status": "no-eligible-objective",
                "platform": selected_platform,
                "reasons": [
                    f"no objective remains within the {policy['objective_lookback_days']}-day "
                    "objective cap"
                ],
            }
        selected_objective = objective_candidates[0]["objective"]

    reasons = [
        "global capacity available",
        (
            f"selected {selected_platform!r} by coverage debt, recent frequency, "
            "cooldown age, strategic priority and deterministic ID tie-break"
            if requested_platform == AUTO
            else f"accepted explicit platform request {selected_platform!r}"
        ),
        (
            f"selected {selected_objective!r} by recent objective frequency, "
            "immediate-repeat avoidance, strategic priority and deterministic ID tie-break"
            if requested_objective == AUTO
            else f"accepted explicit objective request {selected_objective!r}"
        ),
    ]
    return {
        **base,
        "status": "planned",
        "platform": selected_platform,
        "objective": selected_objective,
        "reasons": reasons,
    }


def _load_history(path_value: str) -> Any:
    if not path_value:
        return []
    path = Path(path_value)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        raise PlanningError(f"history file does not exist: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PlanningError(f"history file is not valid JSON: {path}") from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", default="")
    parser.add_argument("--as-of", default="")
    parser.add_argument("--requested-platform", default=AUTO)
    parser.add_argument("--requested-objective", default=AUTO)
    parser.add_argument("--output-json", default="reports/editorial-plan.json")
    args = parser.parse_args()

    as_of = (
        dt.date.fromisoformat(args.as_of)
        if args.as_of
        else dt.datetime.now(dt.timezone.utc).date()
    )
    ecosystem = load_json("config/ecosystem.json")
    policy = load_json("config/editorial-policy.json")
    history = _load_history(args.history)
    try:
        plan = build_campaign_plan(
            ecosystem,
            policy,
            history,
            as_of=as_of,
            requested_platform=args.requested_platform,
            requested_objective=args.requested_objective,
        )
    except PlanningError as exc:
        raise SystemExit(f"portfolio planning failed: {exc}") from exc

    output = Path(args.output_json)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(plan, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        "Editorial plan: "
        f"status={plan['status']} platform={plan['platform']} objective={plan['objective']}"
    )


if __name__ == "__main__":
    main()
