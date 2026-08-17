from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from common import ROOT, load_json

USER_AGENT = "CYBERDUDEBIVASH-Campaign-Intelligence/2.0"
PREFERRED_LIST_KEYS = ("items", "data", "results", "reports", "intel", "entries", "threats", "articles", "posts", "releases")
TITLE_KEYS = ("title", "name", "headline", "subject", "event", "threat", "cve", "id", "slug")
URL_KEYS = ("url", "html_url", "link", "report_url", "source_url", "canonical_url")
DATE_KEYS = ("published_at", "published", "date", "timestamp", "created_at", "updated_at", "release_date")
SUMMARY_KEYS = ("summary", "description", "analysis", "details", "content", "body", "excerpt")
ID_KEYS = ("id", "uuid", "slug", "cve", "tag_name", "name")

URGENCY_TERMS = {
    "critical", "actively exploited", "exploited", "zero-day", "0-day", "ransomware",
    "breach", "credential", "malware", "cve-", "remote code execution", "rce",
    "supply chain", "vulnerability", "incident", "campaign"
}
COMMERCIAL_TERMS = {
    "enterprise", "api", "upgrade", "product", "platform", "release", "launch",
    "academy", "course", "training", "tool", "compliance", "governance", "mssp",
    "soc", "zero trust", "cloud", "ai security"
}
CROSS_SELL_TERMS = {
    "ai security", "threat intelligence", "academy", "trustx", "tools",
    "enterprise defense", "soc", "mssp", "cloud security", "zero trust"
}


@dataclass(frozen=True)
class FetchResult:
    source_id: str
    ok: bool
    items: list[dict[str, Any]]
    error: str = ""


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def clean_text(value: Any, limit: int) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", str(value))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def first_value(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def parse_datetime(value: Any) -> dt.datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        try:
            raw = float(value)
            if raw > 10_000_000_000:
                raw /= 1000
            return dt.datetime.fromtimestamp(raw, tz=dt.timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d", "%a, %d %b %Y %H:%M:%S %z"):
            try:
                parsed = dt.datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def extract_items(payload: Any, max_items: int) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, dict):
        candidates = []
        for key in PREFERRED_LIST_KEYS:
            value = payload.get(key)
            if isinstance(value, list):
                candidates = value
                break
            if isinstance(value, dict):
                nested = extract_items(value, max_items)
                if nested:
                    return nested[:max_items]
        if not candidates:
            candidates = [payload]
    else:
        return []
    return [item for item in candidates[:max_items] if isinstance(item, dict)]


def request_json(url: str, timeout: float, max_bytes: int, token: str = "") -> Any:
    headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    if token and urlparse(url).hostname == "api.github.com":
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
        length = response.headers.get("Content-Length")
        if length and int(length) > max_bytes:
            raise ValueError(f"response too large: {length} bytes")
        raw = response.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError(f"response exceeds {max_bytes} bytes")
        return json.loads(raw.decode("utf-8"))


def source_url(source: dict[str, Any]) -> str:
    if source["type"] == "github-releases":
        return f"https://api.github.com/repos/{source['repository']}/releases?per_page=20"
    return source["url"]


def collect_source(source: dict[str, Any], policy: dict[str, Any], token: str = "") -> FetchResult:
    if not source.get("enabled", False):
        return FetchResult(source["id"], True, [])
    try:
        payload = request_json(
            source_url(source),
            timeout=float(policy["request_timeout_seconds"]),
            max_bytes=int(policy["max_response_bytes"]),
            token=token,
        )
        items = extract_items(payload, int(policy["max_items_per_source"]))
        return FetchResult(source["id"], True, items)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError, OSError) as exc:
        return FetchResult(source["id"], False, [], clean_text(exc, 300))


def normalized_signal(
    source: dict[str, Any],
    item: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any] | None:
    max_title = int(policy["max_title_chars"])
    max_summary = int(policy["max_summary_chars"])
    title = clean_text(first_value(item, TITLE_KEYS), max_title)
    summary = clean_text(first_value(item, SUMMARY_KEYS), max_summary)
    external_id = clean_text(first_value(item, ID_KEYS), 160)

    if not title and summary:
        title = summary[:max_title]
    if not title:
        return None

    url_value = clean_text(first_value(item, URL_KEYS), 500)
    if not url_value.startswith("https://"):
        url_value = source.get("public_url") or source_url(source)
    published = parse_datetime(first_value(item, DATE_KEYS))

    return {
        "source_id": source["id"],
        "source_type": source["type"],
        "platform": source["platform"],
        "purpose": source["purpose"],
        "trust_level": int(source["trust_level"]),
        "external_id": external_id,
        "title": title,
        "summary": summary,
        "url": url_value,
        "published_at": published.isoformat() if published else None,
        "source_url": source_url(source),
    }


def score_timeliness(published_at: str | None, now: dt.datetime) -> int:
    parsed = parse_datetime(published_at)
    if not parsed:
        return 2
    age_days = max(0.0, (now - parsed).total_seconds() / 86400)
    if age_days <= 1:
        return 5
    if age_days <= 3:
        return 4
    if age_days <= 7:
        return 3
    if age_days <= 14:
        return 2
    if age_days <= 30:
        return 1
    return 0


def term_score(text: str, terms: set[str], baseline: int, cap: int = 5) -> int:
    hits = sum(1 for term in terms if term in text)
    return min(cap, baseline + hits)


def score_signal(
    signal: dict[str, Any],
    platforms: dict[str, dict[str, Any]],
    policy: dict[str, Any],
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    now = now or utc_now()
    combined = f"{signal['title']} {signal['summary']} {signal['purpose']}".lower()
    evidence = max(0, min(5, int(signal["trust_level"])))
    timeliness = score_timeliness(signal.get("published_at"), now)
    strategic = 5 if signal["platform"] in platforms else 2
    urgency = term_score(combined, URGENCY_TERMS, baseline=1)
    commercial = term_score(combined, COMMERCIAL_TERMS, baseline=1)
    cross_sell_hits = sum(1 for term in CROSS_SELL_TERMS if term in combined)
    cross_sell = min(5, 2 + cross_sell_hits)

    scores = {
        "strategic_alignment": strategic,
        "audience_urgency": urgency,
        "evidence_strength": evidence,
        "commercial_relevance": commercial,
        "cross_sell_potential": cross_sell,
        "timeliness": timeliness,
    }
    total = sum(scores.values())
    parsed_published = parse_datetime(signal.get("published_at"))
    if parsed_published:
        age_days = max(0.0, (now - parsed_published).total_seconds() / 86400)
        age_gate = age_days <= int(policy["max_signal_age_days"])
    else:
        age_gate = True
    eligible = (
        evidence >= int(policy["minimum_evidence_score"])
        and total >= int(policy["minimum_total_score"])
        and age_gate
    )
    return {**signal, "scores": scores, "total_score": total, "eligible": eligible}


def fingerprint(signal: dict[str, Any]) -> str:
    identity = signal.get("external_id") or f"{signal['title']}|{signal['url']}|{signal.get('published_at') or ''}"
    raw = f"{signal['source_id']}|{identity}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


def issue_body(opportunity: dict[str, Any]) -> str:
    s = opportunity["scores"]
    marker = f"<!-- signal-id:{opportunity['fingerprint']} -->"
    published = opportunity.get("published_at") or "not supplied by source"
    summary = opportunity.get("summary") or "No source summary supplied. Review the canonical evidence before publication."
    return f"""# Campaign Intelligence Opportunity

{marker}

## Signal
**{opportunity['title']}**

- Platform: `{opportunity['platform']}`
- Source: `{opportunity['source_id']}`
- Purpose: `{opportunity['purpose']}`
- Published: `{published}`
- Evidence: {opportunity['url']}

## Source summary
{summary}

## Opportunity score
| Dimension | Score |
|---|---:|
| Strategic alignment | {s['strategic_alignment']}/5 |
| Audience urgency | {s['audience_urgency']}/5 |
| Evidence strength | {s['evidence_strength']}/5 |
| Commercial relevance | {s['commercial_relevance']}/5 |
| Cross-sell potential | {s['cross_sell_potential']}/5 |
| Timeliness | {s['timeliness']}/5 |
| **Total** | **{opportunity['total_score']}/30** |

## Required analyst gate
- [ ] Open and verify the source evidence.
- [ ] Confirm the signal is current and materially relevant.
- [ ] Separate source claims, observed facts, analysis and inference.
- [ ] Select one target audience and one measurable business objective.
- [ ] Verify every product/security claim against production evidence.
- [ ] Select one canonical CTA from the governed public directory.
- [ ] Confirm no customer-private, exploit-sensitive, credential or payment data is exposed.
- [ ] Approve channel-specific derivatives before external publication.

## Recommended next action
Convert this signal into a governed campaign brief only after the evidence and claim gates above pass.

> Automated scoring is prioritization support, not publication approval.
"""


def build_report(
    opportunities: list[dict[str, Any]],
    source_results: list[FetchResult],
    generated_at: dt.datetime,
) -> str:
    lines = [
        "# CYBERDUDEBIVASH® Campaign Intelligence",
        "",
        f"Generated: `{generated_at.replace(microsecond=0).isoformat()}`",
        "",
        "## Source health",
        "",
        "| Source | Status | Items |",
        "|---|---:|---:|",
    ]
    for result in source_results:
        status = "OK" if result.ok else f"ERROR: {result.error}"
        lines.append(f"| {result.source_id} | {status} | {len(result.items)} |")
    lines.extend([
        "",
        "## Ranked opportunities",
        "",
        "| Score | Eligible | Platform | Signal | Source |",
        "|---:|:---:|---|---|---|",
    ])
    for item in opportunities:
        lines.append(
            f"| {item['total_score']}/30 | {'YES' if item['eligible'] else 'NO'} | "
            f"{item['platform']} | {item['title']} | {item['source_id']} |"
        )
    if not opportunities:
        lines.append("| — | — | — | No normalized signals collected | — |")
    lines.extend([
        "",
        "> Eligibility means the deterministic threshold passed. External publication still requires analyst review and approval.",
        "",
    ])
    return "\n".join(lines)


def run(
    sources_cfg: dict[str, Any],
    policy: dict[str, Any],
    ecosystem: dict[str, Any],
    token: str = "",
    now: dt.datetime | None = None,
) -> tuple[list[dict[str, Any]], list[FetchResult]]:
    now = now or utc_now()
    platforms = {p["id"]: p for p in ecosystem["platforms"]}
    source_results: list[FetchResult] = []
    signals: list[dict[str, Any]] = []

    for source in sources_cfg["sources"]:
        result = collect_source(source, policy, token=token)
        source_results.append(result)
        for raw in result.items:
            normalized = normalized_signal(source, raw, policy)
            if normalized:
                signals.append(normalized)

    scored: list[dict[str, Any]] = []
    seen: set[str] = set()
    for signal in signals:
        item = score_signal(signal, platforms, policy, now=now)
        item["fingerprint"] = fingerprint(item)
        if item["fingerprint"] in seen:
            continue
        seen.add(item["fingerprint"])
        item["issue_title"] = clean_text(
            f"Campaign intelligence: {item['platform']} — {item['title']}",
            220,
        )
        item["issue_body"] = issue_body(item)
        scored.append(item)

    scored.sort(key=lambda item: (item["eligible"], item["total_score"], item.get("published_at") or ""), reverse=True)
    eligible_limit = int(policy["max_issues_per_run"])
    selected = 0
    for item in scored:
        item["selected_for_issue"] = bool(item["eligible"] and selected < eligible_limit)
        if item["selected_for_issue"]:
            selected += 1

    return scored, source_results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", default="config/intelligence-sources.json")
    parser.add_argument("--policy", default="config/intelligence-policy.json")
    parser.add_argument("--output-json", default="reports/opportunities.json")
    parser.add_argument("--output-markdown", default="reports/campaign-intelligence.md")
    args = parser.parse_args()

    sources_cfg = load_json(args.sources)
    policy = load_json(args.policy)
    ecosystem = load_json("config/ecosystem.json")
    generated_at = utc_now()
    opportunities, source_results = run(
        sources_cfg,
        policy,
        ecosystem,
        token=os.getenv("GITHUB_TOKEN", ""),
        now=generated_at,
    )

    payload = {
        "schema_version": 1,
        "generated_at": generated_at.replace(microsecond=0).isoformat(),
        "source_health": [
            {"source_id": r.source_id, "ok": r.ok, "items": len(r.items), "error": r.error}
            for r in source_results
        ],
        "opportunities": opportunities,
    }

    json_path = Path(args.output_json)
    md_path = Path(args.output_markdown)
    if not json_path.is_absolute():
        json_path = ROOT / json_path
    if not md_path.is_absolute():
        md_path = ROOT / md_path
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(build_report(opportunities, source_results, generated_at), encoding="utf-8")

    successful = sum(1 for result in source_results if result.ok)
    selected = sum(1 for item in opportunities if item["selected_for_issue"])
    print(f"Wrote {json_path} and {md_path}; sources_ok={successful}/{len(source_results)}; selected={selected}")
    return 0 if successful else 2


if __name__ == "__main__":
    raise SystemExit(main())
