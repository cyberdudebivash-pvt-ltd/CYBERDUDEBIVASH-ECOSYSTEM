from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from common import ROOT, load_json

SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,119}$")
HOST = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
FUNNEL_TOP_LEVEL = {
    "schema_version", "data_classification", "provider", "record_type",
    "property_host", "platform", "window_start", "window_end", "campaign_id",
    "channel", "landing_path", "metrics"
}
ASSIST_TOP_LEVEL = {
    "schema_version", "data_classification", "provider", "record_type",
    "window_start", "window_end", "campaign_id", "from_platform",
    "to_platform", "metrics"
}


class AnalyticsValidationError(ValueError):
    pass


def parse_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise AnalyticsValidationError(f"invalid ISO date: {value}") from exc


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
    fragments = [str(v).lower() for v in privacy["forbidden_key_substrings"]]
    violations = []
    for key, path in _walk_keys(record):
        if key in forbidden or any(fragment in key for fragment in fragments):
            violations.append(path)
    if violations:
        raise AnalyticsValidationError(
            "analytics payload contains forbidden field(s): "
            + ", ".join(sorted(set(violations)))
        )


def platform_hosts(ecosystem: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in ecosystem["platforms"]:
        host = urlparse(item["url"]).hostname
        if not host:
            raise AnalyticsValidationError(f"platform {item['id']} has no canonical host")
        result[item["id"]] = host.lower()
    return result


def enabled_providers(policy: dict[str, Any]) -> set[str]:
    return {
        str(item["id"])
        for item in policy["providers"]
        if item.get("enabled", False)
    }


def validate_common(
    record: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[dt.date, dt.date]:
    validate_privacy(record, policy)
    if record.get("schema_version") != 1:
        raise AnalyticsValidationError("unsupported analytics schema version")
    if record.get("data_classification") != "private-aggregate":
        raise AnalyticsValidationError("data_classification must be private-aggregate")
    provider = str(record.get("provider", ""))
    if provider not in enabled_providers(policy):
        raise AnalyticsValidationError(f"unknown or disabled analytics provider: {provider}")
    start = parse_date(record.get("window_start"))
    end = parse_date(record.get("window_end"))
    if end < start:
        raise AnalyticsValidationError("window_end cannot be before window_start")
    campaign = str(record.get("campaign_id", ""))
    if not SAFE_ID.fullmatch(campaign):
        raise AnalyticsValidationError("invalid campaign_id")
    return start, end


def _validate_metrics(
    metrics: Any,
    required_names: list[str],
) -> dict[str, int]:
    if not isinstance(metrics, dict) or set(metrics) != set(required_names):
        raise AnalyticsValidationError(
            "metrics must contain exactly: " + ", ".join(sorted(required_names))
        )
    for name, value in metrics.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise AnalyticsValidationError(
                f"metric {name} must be a non-negative integer"
            )
    return metrics


def validate_funnel_record(
    record: dict[str, Any],
    policy: dict[str, Any],
    ecosystem: dict[str, Any],
) -> None:
    if set(record) != FUNNEL_TOP_LEVEL:
        missing = FUNNEL_TOP_LEVEL - set(record)
        extra = set(record) - FUNNEL_TOP_LEVEL
        raise AnalyticsValidationError(
            f"invalid funnel contract: missing={sorted(missing)}, extra={sorted(extra)}"
        )
    validate_common(record, policy)
    hosts = platform_hosts(ecosystem)
    platform = str(record["platform"])
    if platform not in hosts:
        raise AnalyticsValidationError(f"unknown platform: {platform}")
    host = str(record["property_host"]).lower().strip(".")
    if not HOST.fullmatch(host):
        raise AnalyticsValidationError("invalid property_host")
    if host != hosts[platform]:
        raise AnalyticsValidationError(
            f"property_host {host} does not match canonical host for {platform}"
        )
    channel = str(record["channel"])
    if channel not in set(policy["allowed_acquisition_channels"]):
        raise AnalyticsValidationError(f"unsupported acquisition channel: {channel}")
    path = str(record["landing_path"])
    max_chars = int(policy["privacy"]["max_landing_path_chars"])
    if (
        not path.startswith("/")
        or "?" in path
        or "#" in path
        or len(path) > max_chars
        or "\x00" in path
    ):
        raise AnalyticsValidationError(
            "landing_path must be a bounded path without query or fragment data"
        )
    metrics = _validate_metrics(
        record["metrics"],
        policy["record_types"]["funnel"]["required_metrics"],
    )
    sessions = metrics["sessions"]
    engaged = metrics["engaged_sessions"]
    cta = metrics["cta_events"]
    leads = metrics["leads"]
    conversions = metrics["conversions"]
    if engaged > sessions:
        raise AnalyticsValidationError("engaged_sessions cannot exceed sessions")
    if cta > engaged:
        raise AnalyticsValidationError("cta_events cannot exceed engaged_sessions")
    if leads > cta:
        raise AnalyticsValidationError("leads cannot exceed cta_events")
    if conversions > leads:
        raise AnalyticsValidationError("conversions cannot exceed leads")


def validate_assist_record(
    record: dict[str, Any],
    policy: dict[str, Any],
    ecosystem: dict[str, Any],
) -> None:
    if set(record) != ASSIST_TOP_LEVEL:
        missing = ASSIST_TOP_LEVEL - set(record)
        extra = set(record) - ASSIST_TOP_LEVEL
        raise AnalyticsValidationError(
            f"invalid assist contract: missing={sorted(missing)}, extra={sorted(extra)}"
        )
    validate_common(record, policy)
    platform_ids = set(platform_hosts(ecosystem))
    source = str(record["from_platform"])
    target = str(record["to_platform"])
    if source not in platform_ids or target not in platform_ids:
        raise AnalyticsValidationError("assist record contains unknown platform")
    if source == target:
        raise AnalyticsValidationError("assist edge must cross platforms")
    metrics = _validate_metrics(
        record["metrics"],
        policy["record_types"]["assist"]["required_metrics"],
    )
    if metrics["assisted_conversions"] > metrics["journeys"]:
        raise AnalyticsValidationError(
            "assisted_conversions cannot exceed journeys"
        )


def validate_record(
    record: dict[str, Any],
    policy: dict[str, Any],
    ecosystem: dict[str, Any],
) -> None:
    if not isinstance(record, dict):
        raise AnalyticsValidationError("analytics record must be an object")
    record_type = record.get("record_type")
    if record_type == "funnel":
        validate_funnel_record(record, policy, ecosystem)
    elif record_type == "assist":
        validate_assist_record(record, policy, ecosystem)
    else:
        raise AnalyticsValidationError(f"unsupported record_type: {record_type}")


def _inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
        return True
    except ValueError:
        return False


def enforce_private_runtime_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if _inside_repo(resolved):
        rel = resolved.relative_to(ROOT.resolve())
        if not rel.parts or rel.parts[0] != "private":
            raise AnalyticsValidationError(
                "analytics runtime files inside the repository must stay under private/"
            )
    return resolved


def load_inputs(paths: list[str], policy: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for raw in paths:
        path = enforce_private_runtime_path(Path(raw))
        if not path.exists() or not path.is_file():
            raise AnalyticsValidationError(f"analytics input not found: {path}")
        if path.suffix.lower() == ".jsonl":
            values = []
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1
            ):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise AnalyticsValidationError(
                        f"{path}:{number}: invalid JSON"
                    ) from exc
                values.append(value)
        else:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise AnalyticsValidationError(f"{path}: invalid JSON") from exc
            values = payload if isinstance(payload, list) else [payload]
        for value in values:
            if not isinstance(value, dict):
                raise AnalyticsValidationError(f"{path}: entries must be objects")
            records.append(value)
            if len(records) > int(policy["max_batch_records"]):
                raise AnalyticsValidationError("analytics batch exceeds max_batch_records")
    return records


def pct(numerator: int, denominator: int) -> float:
    return round((numerator / denominator * 100.0), 4) if denominator else 0.0


def aggregate_records(
    records: list[dict[str, Any]],
    policy: dict[str, Any],
    ecosystem: dict[str, Any],
    *,
    campaign_id_filter: str = "",
) -> dict[str, Any]:
    for record in records:
        validate_record(record, policy, ecosystem)

    accepted = [
        r for r in records
        if not campaign_id_filter or r["campaign_id"] == campaign_id_filter
    ]
    funnel = [r for r in accepted if r["record_type"] == "funnel"]
    assists = [r for r in accepted if r["record_type"] == "assist"]

    funnel_metric_names = policy["record_types"]["funnel"]["required_metrics"]
    totals = {name: 0 for name in funnel_metric_names}
    by_platform: dict[str, dict[str, int]] = {}
    by_channel: dict[str, dict[str, int]] = {}
    for record in funnel:
        p = by_platform.setdefault(
            record["platform"], {name: 0 for name in funnel_metric_names}
        )
        c = by_channel.setdefault(
            record["channel"], {name: 0 for name in funnel_metric_names}
        )
        for name in funnel_metric_names:
            value = record["metrics"][name]
            totals[name] += value
            p[name] += value
            c[name] += value

    assist_edges: dict[str, dict[str, int]] = {}
    for record in assists:
        key = f"{record['from_platform']}->{record['to_platform']}"
        edge = assist_edges.setdefault(
            key, {"journeys": 0, "assisted_conversions": 0}
        )
        edge["journeys"] += record["metrics"]["journeys"]
        edge["assisted_conversions"] += record["metrics"]["assisted_conversions"]

    rates = {
        "engagement_rate": pct(totals["engaged_sessions"], totals["sessions"]),
        "cta_rate": pct(totals["cta_events"], totals["engaged_sessions"]),
        "lead_rate": pct(totals["leads"], totals["cta_events"]),
        "conversion_rate": pct(totals["conversions"], totals["leads"]),
    }
    return {
        "schema_version": 1,
        "data_classification": "private-aggregate-derived",
        "campaign_id": campaign_id_filter or "all",
        "record_count": len(accepted),
        "funnel_record_count": len(funnel),
        "assist_record_count": len(assists),
        "metrics": totals,
        "rates_pct": rates,
        "platforms": dict(sorted(by_platform.items())),
        "channels": dict(sorted(by_channel.items())),
        "assist_edges": dict(sorted(assist_edges.items())),
        "limitations": [
            "Aggregate attribution does not prove causality.",
            "No person-level identifiers are processed or emitted.",
            "This output is private by default and must not be published without explicit review.",
        ],
    }


def render_scorecard(scorecard: dict[str, Any]) -> str:
    m = scorecard["metrics"]
    r = scorecard["rates_pct"]
    lines = [
        "# CYBERDUDEBIVASH® Private First-Party Analytics Scorecard",
        "",
        f"Campaign scope: `{scorecard['campaign_id']}`",
        f"Validated aggregate records: **{scorecard['record_count']}**",
        "",
        "## Funnel",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key in ("sessions", "engaged_sessions", "cta_events", "leads", "conversions"):
        lines.append(f"| {key.replace('_', ' ').title()} | {m[key]} |")
    lines += [
        "",
        "## Rates",
        "",
        f"- Engagement rate: **{r['engagement_rate']:.2f}%**",
        f"- CTA rate: **{r['cta_rate']:.2f}%**",
        f"- Lead rate: **{r['lead_rate']:.2f}%**",
        f"- Conversion rate: **{r['conversion_rate']:.2f}%**",
        "",
        "## Cross-platform assist edges",
        "",
    ]
    if scorecard["assist_edges"]:
        for edge, metrics in scorecard["assist_edges"].items():
            lines.append(
                f"- `{edge}`: {metrics['journeys']} aggregate journeys; "
                f"{metrics['assisted_conversions']} assisted conversions."
            )
    else:
        lines.append("- No validated aggregate assist records.")
    lines += ["", "## Governance limitations", ""]
    lines += [f"- {item}" for item in scorecard["limitations"]]
    lines.append("")
    return "\n".join(lines)


def write_private(path_value: str, content: str) -> Path:
    path = enforce_private_runtime_path(Path(path_value))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    validate_cmd = sub.add_parser("validate")
    validate_cmd.add_argument("--input", nargs="+", required=True)

    score_cmd = sub.add_parser("scorecard")
    score_cmd.add_argument("--input", nargs="+", required=True)
    score_cmd.add_argument("--campaign-id", default="")
    score_cmd.add_argument("--output-json", required=True)
    score_cmd.add_argument("--output-markdown", required=True)

    args = parser.parse_args()
    policy = load_json("config/analytics-policy.json")
    ecosystem = load_json("config/ecosystem.json")

    try:
        records = load_inputs(args.input, policy)
        for record in records:
            validate_record(record, policy, ecosystem)
        if args.command == "validate":
            print(f"Validated {len(records)} private aggregate analytics record(s)")
            return 0
        scorecard = aggregate_records(
            records, policy, ecosystem, campaign_id_filter=args.campaign_id
        )
        json_path = enforce_private_runtime_path(Path(args.output_json))
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(scorecard, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        md_path = write_private(args.output_markdown, render_scorecard(scorecard))
        print(f"Wrote {json_path} and {md_path}")
        return 0
    except (AnalyticsValidationError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
