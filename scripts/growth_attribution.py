from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from common import ROOT, load_json

SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,119}$")
OBJECTIVES = {"authority", "demand", "adoption", "launch", "education", "trust"}
PERFORMANCE_TOP_LEVEL = {
    "schema_version", "campaign_id", "window_start", "window_end",
    "channel", "platform", "metrics"
}


class GrowthValidationError(ValueError):
    pass


def slugify(value: str, max_len: int = 40) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    value = re.sub(r"-{2,}", "-", value)
    return (value or "na")[:max_len].rstrip("-")


def parse_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise GrowthValidationError(f"invalid ISO date: {value}") from exc


def campaign_id(
    campaign_date: str,
    objective: str,
    platform: str,
    prefix: str = "cdb",
) -> str:
    if objective not in OBJECTIVES:
        raise GrowthValidationError(f"unsupported objective: {objective}")
    parse_date(campaign_date)
    platform_slug = slugify(platform, 28)
    identity = f"{campaign_date}|{objective}|{platform_slug}".encode("utf-8")
    digest = hashlib.sha256(identity).hexdigest()[:8]
    compact_date = campaign_date.replace("-", "")
    return f"{slugify(prefix, 12)}-{compact_date}-{slugify(objective, 16)}-{platform_slug}-{digest}"


def canonical_hosts(ecosystem: dict[str, Any]) -> set[str]:
    hosts: set[str] = set()
    for platform in ecosystem["platforms"]:
        host = urlparse(platform["url"]).hostname
        if host:
            hosts.add(host.lower())
    return hosts


def validate_destination(url: str, ecosystem: dict[str, Any]) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise GrowthValidationError("destination must be an absolute HTTPS URL")
    host = parsed.hostname.lower()
    hosts = canonical_hosts(ecosystem)
    if host not in hosts:
        raise GrowthValidationError(
            f"destination host '{host}' is outside the governed ecosystem"
        )


def build_tracked_url(
    destination: str,
    campaign: str,
    source: str,
    medium: str,
    *,
    content: str = "",
    term: str = "",
    max_value_chars: int = 120,
) -> str:
    parsed = urlparse(destination)
    existing = dict(parse_qsl(parsed.query, keep_blank_values=True))
    tracking = {
        "utm_source": slugify(source, max_value_chars),
        "utm_medium": slugify(medium, max_value_chars),
        "utm_campaign": slugify(campaign, max_value_chars),
    }
    if content:
        tracking["utm_content"] = slugify(content, max_value_chars)
    if term:
        tracking["utm_term"] = slugify(term, max_value_chars)
    existing.update(tracking)
    return urlunparse(parsed._replace(query=urlencode(existing)))


def select_destination(
    ecosystem: dict[str, Any], platform: str, explicit_destination: str = ""
) -> str:
    if explicit_destination:
        validate_destination(explicit_destination, ecosystem)
        return explicit_destination
    if platform == "all":
        return ecosystem["canonical_home"]
    matches = [p for p in ecosystem["platforms"] if p["id"] == platform]
    if not matches:
        raise GrowthValidationError(f"unknown platform: {platform}")
    return matches[0]["url"]


def channel_map(channels_cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in channels_cfg["channels"]}


def create_campaign_bundle(
    ecosystem: dict[str, Any],
    channels_cfg: dict[str, Any],
    policy: dict[str, Any],
    *,
    campaign_date: str,
    objective: str,
    platform: str,
    destination: str = "",
    content: str = "primary",
) -> dict[str, Any]:
    dest = select_destination(ecosystem, platform, destination)
    cid = campaign_id(
        campaign_date, objective, platform, policy["campaign_id_prefix"]
    )
    tracked: dict[str, str] = {}
    max_chars = int(policy["utm"]["max_value_chars"])
    for channel in channels_cfg["channels"]:
        if not channel.get("enabled", False):
            continue
        tracked[channel["id"]] = build_tracked_url(
            dest,
            cid,
            channel["utm_source"],
            channel["utm_medium"],
            content=content,
            max_value_chars=max_chars,
        )
    return {
        "schema_version": 1,
        "campaign_id": cid,
        "created_date": campaign_date,
        "objective": objective,
        "platform": platform,
        "state": "planned",
        "destination": dest,
        "tracking_urls": tracked,
        "privacy_classification": "public-campaign-metadata",
    }


def validate_campaign_record(
    record: dict[str, Any],
    policy: dict[str, Any],
    ecosystem: dict[str, Any] | None = None,
) -> None:
    required = {
        "schema_version", "campaign_id", "created_date", "objective", "platform",
        "state", "destination", "tracking_urls", "privacy_classification"
    }
    missing = required - set(record)
    if missing:
        raise GrowthValidationError(
            f"campaign record missing fields: {', '.join(sorted(missing))}"
        )
    if record["schema_version"] != 1:
        raise GrowthValidationError("unsupported campaign schema version")
    if not SAFE_ID.fullmatch(record["campaign_id"]):
        raise GrowthValidationError("invalid campaign_id")
    parse_date(record["created_date"])
    if record["objective"] not in OBJECTIVES:
        raise GrowthValidationError("invalid objective")
    if record["state"] not in policy["allowed_states"]:
        raise GrowthValidationError("invalid campaign state")
    parsed = urlparse(record["destination"])
    if parsed.scheme != "https" or not parsed.hostname:
        raise GrowthValidationError("invalid campaign destination")
    if ecosystem is not None:
        validate_destination(record["destination"], ecosystem)
    if not isinstance(record["tracking_urls"], dict) or not record["tracking_urls"]:
        raise GrowthValidationError("tracking_urls must be a non-empty object")
    for channel, url in record["tracking_urls"].items():
        if not SAFE_ID.fullmatch(channel):
            raise GrowthValidationError(f"invalid channel id: {channel}")
        parsed_url = urlparse(url)
        if parsed_url.scheme != "https" or not parsed_url.hostname:
            raise GrowthValidationError(f"{channel} tracking URL must be absolute HTTPS")
        if parsed_url.hostname.lower() != parsed.hostname.lower():
            raise GrowthValidationError(
                f"{channel} tracking URL host does not match campaign destination"
            )
        params = dict(parse_qsl(parsed_url.query))
        for key in policy["utm"]["required_parameters"]:
            if not params.get(key):
                raise GrowthValidationError(f"{channel} missing {key}")
        if params["utm_campaign"] != record["campaign_id"]:
            raise GrowthValidationError(
                f"{channel} utm_campaign does not match campaign_id"
            )


def transition_campaign(
    record: dict[str, Any], new_state: str, policy: dict[str, Any]
) -> dict[str, Any]:
    validate_campaign_record(record, policy)
    current = record["state"]
    allowed = policy["state_transitions"].get(current, [])
    if new_state not in allowed:
        raise GrowthValidationError(
            f"invalid campaign transition: {current} -> {new_state}"
        )
    updated = dict(record)
    updated["state"] = new_state
    return updated


def _walk_keys(value: Any, path: str = "") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_str = str(key).lower()
            child_path = f"{path}.{key}" if path else str(key)
            found.append((key_str, child_path))
            found.extend(_walk_keys(child, child_path))
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            found.extend(_walk_keys(child, f"{path}[{idx}]"))
    return found


def validate_privacy(record: dict[str, Any], policy: dict[str, Any]) -> None:
    privacy = policy["privacy"]
    forbidden = {str(v).lower() for v in privacy["forbidden_fields"]}
    substrings = [str(v).lower() for v in privacy["forbidden_key_substrings"]]
    violations: list[str] = []
    for key, path in _walk_keys(record):
        if key in forbidden or any(fragment in key for fragment in substrings):
            violations.append(path)
    if violations:
        raise GrowthValidationError(
            "performance payload contains forbidden field(s): "
            + ", ".join(sorted(set(violations)))
        )


def validate_performance_record(
    record: dict[str, Any],
    policy: dict[str, Any],
    channels_cfg: dict[str, Any],
) -> None:
    if set(record) != PERFORMANCE_TOP_LEVEL:
        missing = PERFORMANCE_TOP_LEVEL - set(record)
        extra = set(record) - PERFORMANCE_TOP_LEVEL
        details = []
        if missing:
            details.append("missing=" + ",".join(sorted(missing)))
        if extra:
            details.append("extra=" + ",".join(sorted(extra)))
        raise GrowthValidationError(
            "invalid performance top-level contract (" + "; ".join(details) + ")"
        )
    validate_privacy(record, policy)
    if record["schema_version"] != 1:
        raise GrowthValidationError("unsupported performance schema version")
    if not SAFE_ID.fullmatch(str(record["campaign_id"])):
        raise GrowthValidationError("invalid performance campaign_id")
    start = parse_date(record["window_start"])
    end = parse_date(record["window_end"])
    if end < start:
        raise GrowthValidationError("window_end cannot be before window_start")
    channels = channel_map(channels_cfg)
    if record["channel"] not in channels or not channels[record["channel"]].get("enabled", False):
        raise GrowthValidationError(f"unknown or disabled channel: {record['channel']}")
    if not SAFE_ID.fullmatch(str(record["platform"])):
        raise GrowthValidationError("invalid performance platform id")
    metrics = record["metrics"]
    required_metrics = set(policy["performance"]["required_metrics"])
    if set(metrics) != required_metrics:
        raise GrowthValidationError(
            "metrics must contain exactly: " + ", ".join(sorted(required_metrics))
        )
    for name, value in metrics.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise GrowthValidationError(f"metric {name} must be a non-negative integer")
    impressions = metrics["impressions"]
    clicks = metrics["clicks"]
    engaged = metrics["engaged_visits"]
    leads = metrics["leads"]
    conversions = metrics["conversions"]
    if impressions and clicks > impressions:
        raise GrowthValidationError("clicks cannot exceed impressions")
    if clicks and engaged > clicks:
        raise GrowthValidationError("engaged_visits cannot exceed clicks")
    if clicks and leads > clicks:
        raise GrowthValidationError("leads cannot exceed clicks")
    if clicks and conversions > clicks:
        raise GrowthValidationError("conversions cannot exceed clicks")


def pct(numerator: int, denominator: int) -> float:
    return round((numerator / denominator * 100.0), 4) if denominator else 0.0


def aggregate_records(
    records: list[dict[str, Any]],
    policy: dict[str, Any],
    channels_cfg: dict[str, Any],
    *,
    campaign_id_filter: str = "",
) -> dict[str, Any]:
    accepted: list[dict[str, Any]] = []
    for record in records:
        validate_performance_record(record, policy, channels_cfg)
        if campaign_id_filter and record["campaign_id"] != campaign_id_filter:
            continue
        accepted.append(record)

    metric_names = policy["performance"]["required_metrics"]
    totals = {metric: 0 for metric in metric_names}
    by_channel: dict[str, dict[str, int]] = {}
    for record in accepted:
        channel_totals = by_channel.setdefault(
            record["channel"], {metric: 0 for metric in metric_names}
        )
        for metric in metric_names:
            value = record["metrics"][metric]
            totals[metric] += value
            channel_totals[metric] += value

    rates = calculate_rates(totals)
    index = performance_index(rates, policy)
    channel_scorecards = {
        channel: {
            "metrics": values,
            "rates_pct": calculate_rates(values),
        }
        for channel, values in sorted(by_channel.items())
    }
    for data in channel_scorecards.values():
        data["performance_index"] = performance_index(data["rates_pct"], policy)

    return {
        "schema_version": 1,
        "campaign_id": campaign_id_filter or "all",
        "record_count": len(accepted),
        "metrics": totals,
        "rates_pct": rates,
        "performance_index": index,
        "channels": channel_scorecards,
        "recommendations": recommendations(channel_scorecards, rates, totals, policy),
    }


def calculate_rates(metrics: dict[str, int]) -> dict[str, float]:
    impressions = metrics["impressions"]
    clicks = metrics["clicks"]
    engaged = metrics["engaged_visits"]
    return {
        "ctr": pct(clicks, impressions),
        "engaged_visit_rate": pct(engaged, clicks),
        "cta_rate": pct(metrics["cta_actions"], engaged),
        "lead_rate": pct(metrics["leads"], engaged),
        "conversion_rate": pct(metrics["conversions"], clicks),
    }


def performance_index(rates: dict[str, float], policy: dict[str, Any]) -> float:
    targets = policy["performance"]["targets_pct"]
    weights = policy["performance"]["score_weights"]
    total = 0.0
    for metric, weight in weights.items():
        target = float(targets[metric])
        attainment = min(1.0, rates[metric] / target) if target > 0 else 0.0
        total += attainment * float(weight) * 100.0
    return round(total, 2)


def recommendations(
    channels: dict[str, dict[str, Any]],
    rates: dict[str, float],
    totals: dict[str, int],
    policy: dict[str, Any],
) -> list[str]:
    recs: list[str] = []
    min_clicks = int(policy["performance"]["minimum_clicks_for_channel_recommendation"])
    eligible_channels = [
        (name, data)
        for name, data in channels.items()
        if data["metrics"]["clicks"] >= min_clicks
    ]
    eligible_channels.sort(
        key=lambda item: item[1]["performance_index"], reverse=True
    )
    if len(eligible_channels) >= 2:
        best_name, best = eligible_channels[0]
        second = eligible_channels[1][1]
        if best["performance_index"] - second["performance_index"] >= 10:
            recs.append(
                f"Prioritize {best_name} for the next comparable campaign hypothesis; "
                f"its performance index leads the next eligible channel by at least 10 points."
            )
    elif len(eligible_channels) == 1:
        recs.append(
            f"{eligible_channels[0][0]} is the only channel above the minimum click sample; "
            "collect comparable volume on another channel before reallocating distribution."
        )
    else:
        recs.append(
            "Insufficient channel-level click volume for a defensible allocation recommendation."
        )

    targets = policy["performance"]["targets_pct"]
    for metric in ("ctr", "engaged_visit_rate", "cta_rate", "lead_rate", "conversion_rate"):
        if rates[metric] < float(targets[metric]):
            recs.append(
                f"Investigate {metric.replace('_', ' ')}: {rates[metric]:.2f}% is below "
                f"the configured target of {float(targets[metric]):.2f}%."
            )
    if totals["clicks"] == 0:
        recs.append("No attributed clicks are present; do not infer campaign effectiveness.")
    return recs


def render_scorecard(scorecard: dict[str, Any]) -> str:
    m = scorecard["metrics"]
    r = scorecard["rates_pct"]
    lines = [
        "# CYBERDUDEBIVASH® Growth Attribution Scorecard",
        "",
        f"Campaign: `{scorecard['campaign_id']}`",
        f"Performance records: **{scorecard['record_count']}**",
        f"Performance index: **{scorecard['performance_index']}/100**",
        "",
        "## Aggregate funnel",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key in ("impressions", "clicks", "engaged_visits", "cta_actions", "leads", "conversions"):
        lines.append(f"| {key.replace('_', ' ').title()} | {m[key]} |")
    lines.extend([
        "",
        "## Rates",
        "",
        "| KPI | Rate |",
        "|---|---:|",
        f"| CTR | {r['ctr']:.2f}% |",
        f"| Engaged visit rate | {r['engaged_visit_rate']:.2f}% |",
        f"| CTA rate | {r['cta_rate']:.2f}% |",
        f"| Lead rate | {r['lead_rate']:.2f}% |",
        f"| Conversion rate | {r['conversion_rate']:.2f}% |",
        "",
        "## Channel performance",
        "",
        "| Channel | Clicks | Leads | Conversions | Index |",
        "|---|---:|---:|---:|---:|",
    ])
    if scorecard["channels"]:
        for channel, data in scorecard["channels"].items():
            metrics = data["metrics"]
            lines.append(
                f"| {channel} | {metrics['clicks']} | {metrics['leads']} | "
                f"{metrics['conversions']} | {data['performance_index']:.2f} |"
            )
    else:
        lines.append("| — | 0 | 0 | 0 | 0.00 |")
    lines.extend(["", "## Evidence-bounded recommendations", ""])
    for rec in scorecard["recommendations"]:
        lines.append(f"- {rec}")
    lines.extend([
        "",
        "> This scorecard uses aggregate campaign telemetry only. It does not identify people, "
        "prove causality, or authorize external publication.",
        "",
    ])
    return "\n".join(lines)


def load_performance_inputs(paths: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for raw_path in paths:
        path = Path(raw_path)
        if not path.is_absolute():
            path = ROOT / path
        if not path.exists():
            raise GrowthValidationError(f"performance input not found: {path}")
        if path.suffix.lower() == ".jsonl":
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise GrowthValidationError(
                        f"{path}:{number}: invalid JSON"
                    ) from exc
                if not isinstance(value, dict):
                    raise GrowthValidationError(f"{path}:{number}: record must be an object")
                records.append(value)
        else:
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, list):
                if not all(isinstance(item, dict) for item in value):
                    raise GrowthValidationError(f"{path}: list entries must be objects")
                records.extend(value)
            elif isinstance(value, dict):
                records.append(value)
            else:
                raise GrowthValidationError(f"{path}: expected object or list")
    return records


def write_json(path: str, payload: Any) -> Path:
    output = Path(path)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    campaign_cmd = sub.add_parser("campaign")
    campaign_cmd.add_argument("--date", required=True)
    campaign_cmd.add_argument("--objective", choices=sorted(OBJECTIVES), required=True)
    campaign_cmd.add_argument("--platform", required=True)
    campaign_cmd.add_argument("--destination", default="")
    campaign_cmd.add_argument("--content", default="primary")
    campaign_cmd.add_argument("--output", required=True)

    transition_cmd = sub.add_parser("transition")
    transition_cmd.add_argument("--record", required=True)
    transition_cmd.add_argument("--to-state", required=True)
    transition_cmd.add_argument("--output", required=True)

    validate_cmd = sub.add_parser("validate-performance")
    validate_cmd.add_argument("--input", nargs="+", required=True)

    scorecard_cmd = sub.add_parser("scorecard")
    scorecard_cmd.add_argument("--input", nargs="+", required=True)
    scorecard_cmd.add_argument("--campaign-id", default="")
    scorecard_cmd.add_argument("--output-json", required=True)
    scorecard_cmd.add_argument("--output-markdown", required=True)

    args = parser.parse_args()
    policy = load_json("config/growth-policy.json")
    channels_cfg = load_json("config/channel-taxonomy.json")

    try:
        if args.command == "campaign":
            ecosystem = load_json("config/ecosystem.json")
            bundle = create_campaign_bundle(
                ecosystem, channels_cfg, policy,
                campaign_date=args.date,
                objective=args.objective,
                platform=args.platform,
                destination=args.destination,
                content=args.content,
            )
            validate_campaign_record(bundle, policy, ecosystem)
            out = write_json(args.output, bundle)
            print(f"Wrote {out}")
            return 0

        if args.command == "transition":
            path = Path(args.record)
            if not path.is_absolute():
                path = ROOT / path
            record = json.loads(path.read_text(encoding="utf-8"))
            ecosystem = load_json("config/ecosystem.json")
            validate_campaign_record(record, policy, ecosystem)
            updated = transition_campaign(record, args.to_state, policy)
            out = write_json(args.output, updated)
            print(f"Wrote {out}")
            return 0

        records = load_performance_inputs(args.input)
        if args.command == "validate-performance":
            for record in records:
                validate_performance_record(record, policy, channels_cfg)
            print(f"Validated {len(records)} performance record(s)")
            return 0

        if args.command == "scorecard":
            scorecard = aggregate_records(
                records, policy, channels_cfg,
                campaign_id_filter=args.campaign_id,
            )
            json_out = write_json(args.output_json, scorecard)
            md_path = Path(args.output_markdown)
            if not md_path.is_absolute():
                md_path = ROOT / md_path
            md_path.parent.mkdir(parents=True, exist_ok=True)
            md_path.write_text(render_scorecard(scorecard), encoding="utf-8")
            print(f"Wrote {json_out} and {md_path}")
            return 0
    except (GrowthValidationError, json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: {exc}")
        return 2

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
