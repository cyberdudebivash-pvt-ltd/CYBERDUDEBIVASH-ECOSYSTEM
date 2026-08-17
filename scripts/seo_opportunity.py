from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from common import ROOT, load_json

SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,119}$")
SIGNALS = {
    "strategic_fit", "commercial_intent", "authority_fit",
    "landing_readiness", "content_gap"
}


class SeoValidationError(ValueError):
    pass


def parse_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise SeoValidationError(f"invalid ISO date: {value}") from exc


def _validate_score(value: Any, policy: dict[str, Any], name: str) -> int:
    minimum = int(policy["rules"]["numeric_signals_min"])
    maximum = int(policy["rules"]["numeric_signals_max"])
    if isinstance(value, bool) or not isinstance(value, int):
        raise SeoValidationError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise SeoValidationError(f"{name} must be between {minimum} and {maximum}")
    return value


def platform_ids(ecosystem: dict[str, Any]) -> set[str]:
    return {item["id"] for item in ecosystem["platforms"]}


def validate_topic(
    topic: dict[str, Any],
    policy: dict[str, Any],
    ecosystem: dict[str, Any],
) -> None:
    expected = {
        "schema_version", "topic_id", "cluster", "query", "intent",
        "target_platform", "landing_path", "source_platforms",
        "internal_signals", "external_evidence"
    }
    if set(topic) != expected:
        raise SeoValidationError(
            f"{topic.get('topic_id','<unknown>')}: invalid topic contract"
        )
    if topic["schema_version"] != 1:
        raise SeoValidationError("unsupported SEO topic schema version")
    if not SAFE_ID.fullmatch(str(topic["topic_id"])):
        raise SeoValidationError("invalid topic_id")
    query = str(topic["query"]).strip()
    if not 2 <= len(query) <= 160 or "\n" in query:
        raise SeoValidationError(f"{topic['topic_id']}: invalid query")
    if topic["intent"] not in policy["allowed_intents"]:
        raise SeoValidationError(f"{topic['topic_id']}: unsupported intent")
    ids = platform_ids(ecosystem)
    if topic["target_platform"] not in ids:
        raise SeoValidationError(f"{topic['topic_id']}: unknown target platform")
    path = str(topic["landing_path"])
    if not path.startswith("/") or "?" in path or "#" in path or len(path) > 200:
        raise SeoValidationError(f"{topic['topic_id']}: invalid landing_path")
    sources = topic["source_platforms"]
    if not isinstance(sources, list) or not sources:
        raise SeoValidationError(f"{topic['topic_id']}: source_platforms required")
    if len(set(sources)) != len(sources):
        raise SeoValidationError(f"{topic['topic_id']}: duplicate source platform")
    for source in sources:
        if source not in ids:
            raise SeoValidationError(f"{topic['topic_id']}: unknown source platform {source}")
        if source == topic["target_platform"]:
            raise SeoValidationError(f"{topic['topic_id']}: source cannot equal target")
    signals = topic["internal_signals"]
    if not isinstance(signals, dict) or set(signals) != SIGNALS:
        raise SeoValidationError(f"{topic['topic_id']}: invalid internal signals")
    for name, value in signals.items():
        _validate_score(value, policy, name)

    evidence = topic["external_evidence"]
    if not isinstance(evidence, dict):
        raise SeoValidationError(f"{topic['topic_id']}: external_evidence must be object")
    status = evidence.get("status")
    if status not in policy["allowed_external_evidence_status"]:
        raise SeoValidationError(f"{topic['topic_id']}: invalid evidence status")
    if status == "none":
        if set(evidence) != {"status"}:
            raise SeoValidationError(
                f"{topic['topic_id']}: unverified evidence cannot carry market metrics"
            )
    elif status == "verified":
        required = {
            "status", "provider", "as_of", "demand_score",
            "competition_opportunity"
        }
        if set(evidence) != required:
            raise SeoValidationError(
                f"{topic['topic_id']}: verified evidence contract is incomplete"
            )
        if evidence["provider"] not in policy["approved_external_providers"]:
            raise SeoValidationError(
                f"{topic['topic_id']}: external provider is not approved"
            )
        as_of = parse_date(evidence["as_of"])
        if as_of > dt.date.today():
            raise SeoValidationError(f"{topic['topic_id']}: evidence date is in the future")
        _validate_score(evidence["demand_score"], policy, "demand_score")
        _validate_score(
            evidence["competition_opportunity"], policy, "competition_opportunity"
        )


def validate_registry(
    registry: dict[str, Any],
    policy: dict[str, Any],
    ecosystem: dict[str, Any],
) -> None:
    if set(registry) != {"schema_version", "topics"} or registry["schema_version"] != 1:
        raise SeoValidationError("invalid SEO topic registry")
    topics = registry["topics"]
    if not isinstance(topics, list) or not topics:
        raise SeoValidationError("SEO topic registry cannot be empty")
    ids: set[str] = set()
    queries: set[str] = set()
    for topic in topics:
        validate_topic(topic, policy, ecosystem)
        tid = topic["topic_id"]
        query = topic["query"].strip().lower()
        if tid in ids:
            raise SeoValidationError(f"duplicate topic_id: {tid}")
        if query in queries:
            raise SeoValidationError(f"duplicate SEO query: {query}")
        ids.add(tid)
        queries.add(query)


def _weighted_score(
    signals: dict[str, int],
    weights: dict[str, float],
) -> float:
    return sum(float(signals[name]) / 5.0 * float(weight) * 100.0 for name, weight in weights.items())


def score_topic(
    topic: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    internal_score = _weighted_score(
        topic["internal_signals"], policy["internal_weights"]
    )
    evidence = topic["external_evidence"]
    if evidence["status"] == "verified":
        external_signals = {
            "demand_score": evidence["demand_score"],
            "competition_opportunity": evidence["competition_opportunity"],
        }
        external_score = _weighted_score(
            external_signals, policy["external_weights"]
        )
        blend = policy["blend"]
        raw_score = (
            internal_score * float(blend["internal"])
            + external_score * float(blend["external"])
        )
        confidence = "verified-external"
        market_evidence = {
            "status": "verified",
            "provider": evidence["provider"],
            "as_of": evidence["as_of"],
        }
    else:
        external_score = None
        raw_score = internal_score
        confidence = "internal-only"
        market_evidence = {"status": "none"}

    decision_score = round(
        raw_score * float(policy["confidence_multiplier"][confidence]), 2
    )
    return {
        "topic_id": topic["topic_id"],
        "query": topic["query"],
        "cluster": topic["cluster"],
        "intent": topic["intent"],
        "target_platform": topic["target_platform"],
        "landing_path": topic["landing_path"],
        "source_platforms": topic["source_platforms"],
        "internal_score": round(internal_score, 2),
        "external_score": round(external_score, 2) if external_score is not None else None,
        "decision_score": decision_score,
        "confidence": confidence,
        "market_evidence": market_evidence,
        "ranking_claim_allowed": confidence == "verified-external",
        "recommended": decision_score >= float(policy["recommendation_threshold"]),
    }


def build_report(
    registry: dict[str, Any],
    policy: dict[str, Any],
    ecosystem: dict[str, Any],
) -> dict[str, Any]:
    validate_registry(registry, policy, ecosystem)
    scored = [score_topic(topic, policy) for topic in registry["topics"]]
    scored.sort(
        key=lambda item: (
            item["recommended"],
            item["confidence"] == "verified-external",
            item["decision_score"],
        ),
        reverse=True,
    )
    limit = int(policy["max_report_items"])
    return {
        "schema_version": 1,
        "score_version": policy["score_version"],
        "generated_date": dt.date.today().isoformat(),
        "opportunity_count": len(scored),
        "recommended_count": sum(1 for item in scored if item["recommended"]),
        "opportunities": scored[:limit],
        "guardrails": [
            "Internal-only scores are editorial planning signals, not proof of search demand.",
            "Ranking and demand claims require verified external evidence from an approved provider.",
            "No search volume, keyword difficulty, or ranking position is invented when evidence is absent.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# CYBERDUDEBIVASH® SEO Opportunity Intelligence",
        "",
        f"Score version: `{report['score_version']}`",
        f"Generated: **{report['generated_date']}**",
        f"Candidates: **{report['opportunity_count']}**",
        f"Recommended: **{report['recommended_count']}**",
        "",
        "## Prioritized opportunities",
        "",
        "| Topic | Intent | Target | Score | Confidence | Recommended |",
        "|---|---|---|---:|---|---|",
    ]
    for item in report["opportunities"]:
        lines.append(
            f"| {item['query']} | {item['intent']} | {item['target_platform']} | "
            f"{item['decision_score']:.2f} | {item['confidence']} | "
            f"{'yes' if item['recommended'] else 'no'} |"
        )
    lines += ["", "## Internal-link actions", ""]
    for item in report["opportunities"]:
        if not item["recommended"]:
            continue
        sources = ", ".join(f"`{s}`" for s in item["source_platforms"])
        lines.append(
            f"- **{item['query']}** → target `{item['target_platform']}{item['landing_path']}`; "
            f"evaluate contextual links from {sources}."
        )
    lines += ["", "## Evidence guardrails", ""]
    lines += [f"- {item}" for item in report["guardrails"]]
    lines.append("")
    return "\n".join(lines)


def write(path_value: str, content: str) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-markdown", required=True)
    args = parser.parse_args()
    policy = load_json("config/seo-policy.json")
    registry = load_json("config/seo-topics.json")
    ecosystem = load_json("config/ecosystem.json")
    try:
        report = build_report(registry, policy, ecosystem)
        json_path = write(
            args.output_json,
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        )
        md_path = write(args.output_markdown, render_markdown(report))
        print(f"Wrote {json_path} and {md_path}")
        return 0
    except (SeoValidationError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
