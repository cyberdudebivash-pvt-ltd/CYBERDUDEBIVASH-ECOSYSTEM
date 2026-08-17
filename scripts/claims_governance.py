from __future__ import annotations

import datetime as dt
import re
import subprocess
from pathlib import Path

from common import ROOT, load_json


POLICY_PATH = "config/claims-governance.json"
REQUIRED_CLAIM_IDS = {
    "legal-entity-name",
    "gst-registration",
    "msme-udyam-registration",
    "startup-india-recognition",
    "payment-plan-identifiers",
    "market-leadership-india-first-ai-native",
    "public-location-wording",
}
EVIDENCE_REQUIRED_CATEGORIES = {
    "legal-entity",
    "tax",
    "government-recognition",
    "regulatory",
    "certification",
    "market-leadership",
}


def load_policy() -> dict:
    return load_json(POLICY_PATH)


def _parse_date(value: str, field: str, errors: list[str]) -> dt.date | None:
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError):
        errors.append(f"{field} must be an ISO date (YYYY-MM-DD)")
        return None


def _compiled_patterns(mapping: dict[str, str], namespace: str, errors: list[str]) -> dict[str, re.Pattern]:
    compiled: dict[str, re.Pattern] = {}
    for rule_id, pattern in mapping.items():
        try:
            compiled[rule_id] = re.compile(pattern)
        except re.error as exc:
            errors.append(f"{namespace}.{rule_id} has invalid regex: {exc}")
    return compiled


def claim_index(policy: dict) -> dict[str, dict]:
    return {
        claim["id"]: claim
        for claim in policy.get("claims", [])
        if isinstance(claim, dict) and claim.get("id")
    }


def find_sensitive_identifiers(text: str, policy: dict | None = None) -> list[str]:
    policy = policy or load_policy()
    patterns = policy.get("sensitive_identifier_policy", {}).get("patterns", {})
    findings: list[str] = []
    for rule_id, pattern in patterns.items():
        try:
            if re.search(pattern, text):
                findings.append(rule_id)
        except re.error:
            findings.append(f"invalid-pattern:{rule_id}")
    return sorted(set(findings))


def find_claim_violations(text: str, policy: dict | None = None) -> list[str]:
    policy = policy or load_policy()
    violations: list[str] = []

    for rule in policy.get("prohibited_claim_rules", []):
        rule_id = rule.get("id", "unnamed-prohibited-rule")
        pattern = rule.get("pattern", "")
        if not pattern:
            continue
        try:
            if re.search(pattern, text):
                violations.append(f"prohibited:{rule_id}")
        except re.error:
            violations.append(f"invalid-pattern:{rule_id}")

    claims = claim_index(policy)
    for rule in policy.get("claim_detection_rules", []):
        claim_id = rule.get("claim_id", "")
        pattern = rule.get("pattern", "")
        if not claim_id or not pattern:
            continue
        try:
            matched = re.search(pattern, text)
        except re.error:
            violations.append(f"invalid-pattern:claim-detection:{claim_id}")
            continue
        if not matched:
            continue

        claim = claims.get(claim_id)
        if not claim:
            violations.append(f"unknown-claim:{claim_id}")
            continue

        if claim.get("status") != "approved":
            violations.append(f"not-approved:{claim_id}")
            continue

        approved_wording = str(claim.get("approved_public_wording") or "").strip()
        if not approved_wording or approved_wording.casefold() not in text.casefold():
            violations.append(f"unapproved-wording:{claim_id}")

    return sorted(set(violations))


def validate_publication_text(
    text: str,
    policy: dict | None = None,
    *,
    context: str = "content",
) -> None:
    policy = policy or load_policy()
    sensitive = find_sensitive_identifiers(text, policy)
    claim_violations = find_claim_violations(text, policy)
    failures: list[str] = []
    if sensitive:
        failures.append("sensitive identifiers detected: " + ", ".join(sensitive))
    if claim_violations:
        failures.append("claim governance violations: " + ", ".join(claim_violations))
    if failures:
        raise ValueError(f"{context} rejected by claims governance: " + "; ".join(failures))


def approved_public_claims(policy: dict | None = None) -> list[dict]:
    policy = policy or load_policy()
    return [claim for claim in policy.get("claims", []) if claim.get("status") == "approved"]


def validate_policy(policy: dict | None = None) -> list[str]:
    policy = policy or load_policy()
    errors: list[str] = []

    if policy.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if policy.get("default_publication_decision") != "deny":
        errors.append("default_publication_decision must be 'deny'")

    allowed_statuses = set(policy.get("allowed_statuses", []))
    if allowed_statuses != {"approved", "hold", "prohibited", "private-only"}:
        errors.append("allowed_statuses must contain approved, hold, prohibited and private-only")

    authoritative = set(policy.get("authoritative_evidence_types", []))
    if not authoritative:
        errors.append("authoritative_evidence_types must be non-empty")

    sensitive_patterns = policy.get("sensitive_identifier_policy", {}).get("patterns", {})
    if not isinstance(sensitive_patterns, dict) or not sensitive_patterns:
        errors.append("sensitive_identifier_policy.patterns must be a non-empty object")
    else:
        _compiled_patterns(
            sensitive_patterns,
            "sensitive_identifier_policy.patterns",
            errors,
        )

    prohibited_rules = policy.get("prohibited_claim_rules", [])
    if not isinstance(prohibited_rules, list) or not prohibited_rules:
        errors.append("prohibited_claim_rules must be a non-empty list")
    else:
        seen_rule_ids: set[str] = set()
        for index, rule in enumerate(prohibited_rules):
            rule_id = rule.get("id")
            pattern = rule.get("pattern")
            if not rule_id:
                errors.append(f"prohibited_claim_rules[{index}] requires id")
            elif rule_id in seen_rule_ids:
                errors.append(f"duplicate prohibited claim rule id: {rule_id}")
            else:
                seen_rule_ids.add(rule_id)
            if not pattern:
                errors.append(f"prohibited_claim_rules[{index}] requires pattern")
            else:
                try:
                    re.compile(pattern)
                except re.error as exc:
                    errors.append(f"prohibited_claim_rules[{index}] invalid regex: {exc}")

    claims = policy.get("claims", [])
    if not isinstance(claims, list) or not claims:
        errors.append("claims must be a non-empty list")
        return errors

    seen_claim_ids: set[str] = set()
    today = dt.datetime.now(dt.timezone.utc).date()

    for index, claim in enumerate(claims):
        claim_id = claim.get("id")
        category = claim.get("category")
        status = claim.get("status")
        approved_wording = str(claim.get("approved_public_wording") or "").strip()

        if not claim_id:
            errors.append(f"claims[{index}] requires id")
            continue
        if claim_id in seen_claim_ids:
            errors.append(f"duplicate claim id: {claim_id}")
        seen_claim_ids.add(claim_id)

        if not category:
            errors.append(f"{claim_id}: category is required")
        if status not in allowed_statuses:
            errors.append(f"{claim_id}: invalid status {status!r}")

        if status == "approved":
            if not approved_wording:
                errors.append(f"{claim_id}: approved claim requires approved_public_wording")
            for field in (
                "evidence_type",
                "evidence_reference",
                "evidence_owner",
                "approved_on",
                "review_due_on",
            ):
                if not claim.get(field):
                    errors.append(f"{claim_id}: approved claim requires {field}")

            if (
                category in EVIDENCE_REQUIRED_CATEGORIES
                and claim.get("evidence_type") not in authoritative
            ):
                errors.append(
                    f"{claim_id}: category {category!r} requires authoritative evidence_type"
                )

            approved_on = None
            review_due = None
            if claim.get("approved_on"):
                approved_on = _parse_date(
                    claim["approved_on"],
                    f"{claim_id}.approved_on",
                    errors,
                )
            if claim.get("review_due_on"):
                review_due = _parse_date(
                    claim["review_due_on"],
                    f"{claim_id}.review_due_on",
                    errors,
                )
            if approved_on and review_due and review_due < approved_on:
                errors.append(f"{claim_id}: review_due_on cannot precede approved_on")
            if review_due and review_due < today:
                errors.append(f"{claim_id}: approval expired on {review_due.isoformat()}")

            evidence_reference = str(claim.get("evidence_reference") or "")
            if find_sensitive_identifiers(evidence_reference, policy):
                errors.append(f"{claim_id}: evidence_reference contains a sensitive identifier")
            if find_sensitive_identifiers(approved_wording, policy):
                errors.append(f"{claim_id}: approved_public_wording contains a sensitive identifier")
        elif approved_wording:
            errors.append(f"{claim_id}: {status} claim must not define approved_public_wording")

        if status in {"hold", "prohibited", "private-only"} and not claim.get("reason"):
            errors.append(f"{claim_id}: {status} claim requires reason")
        if status == "private-only" and claim.get("public_disclosure") != "forbidden":
            errors.append(
                f"{claim_id}: private-only claim must set public_disclosure='forbidden'"
            )

    missing = sorted(REQUIRED_CLAIM_IDS - seen_claim_ids)
    if missing:
        errors.append("missing required claims: " + ", ".join(missing))

    detection_rules = policy.get("claim_detection_rules", [])
    if not isinstance(detection_rules, list) or not detection_rules:
        errors.append("claim_detection_rules must be a non-empty list")
    else:
        for index, rule in enumerate(detection_rules):
            claim_id = rule.get("claim_id")
            pattern = rule.get("pattern")
            if claim_id not in seen_claim_ids:
                errors.append(
                    f"claim_detection_rules[{index}] references unknown claim {claim_id!r}"
                )
            if not pattern:
                errors.append(f"claim_detection_rules[{index}] requires pattern")
            else:
                try:
                    re.compile(pattern)
                except re.error as exc:
                    errors.append(f"claim_detection_rules[{index}] invalid regex: {exc}")

    claims_by_id = claim_index(policy)
    market_claim = claims_by_id.get("market-leadership-india-first-ai-native", {})
    if market_claim.get("status") != "prohibited":
        errors.append(
            "market-leadership-india-first-ai-native must remain prohibited until evidence is approved"
        )
    plan_claim = claims_by_id.get("payment-plan-identifiers", {})
    if plan_claim.get("status") != "private-only":
        errors.append("payment-plan-identifiers must remain private-only")

    return errors


def _tracked_text_paths(policy: dict) -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        check=True,
        capture_output=True,
        text=False,
    )
    suffixes = tuple(policy.get("repository_scan", {}).get("text_suffixes", []))
    normalized_suffixes = tuple(item.lower() for item in suffixes)
    paths: list[Path] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        relative = raw.decode("utf-8")
        path = ROOT / relative
        if normalized_suffixes and not relative.lower().endswith(normalized_suffixes):
            continue
        paths.append(path)
    return paths


def scan_repository(policy: dict | None = None) -> list[str]:
    policy = policy or load_policy()
    errors: list[str] = []
    exclusions = set(
        policy.get("repository_scan", {}).get("claim_scan_exclusions", [])
    )

    try:
        paths = _tracked_text_paths(policy)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        return [f"unable to enumerate tracked files for governance scan: {exc}"]

    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        sensitive = find_sensitive_identifiers(text, policy)
        if sensitive:
            errors.append(
                f"{relative}: sensitive identifiers detected: {', '.join(sensitive)}"
            )

        if relative in exclusions:
            continue
        violations = find_claim_violations(text, policy)
        if violations:
            errors.append(
                f"{relative}: claim governance violations: {', '.join(violations)}"
            )

    return errors
