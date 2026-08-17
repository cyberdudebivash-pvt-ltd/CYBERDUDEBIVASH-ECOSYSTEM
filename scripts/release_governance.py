#!/usr/bin/env python3
"""Validate, inspect, and apply CYBERDUDEBIVASH GitHub release governance.

The module is intentionally stdlib-only so it can run in GitHub Actions or on an
operator workstation without dependency installation.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_POLICY = Path("config/release-governance.json")
DEFAULT_RULESET = Path("config/github-main-ruleset.json")
API_ROOT = "https://api.github.com"


class GovernanceError(RuntimeError):
    pass


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise GovernanceError(f"{path} must contain a JSON object")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GovernanceError(message)


def validate_contract(policy: dict[str, Any], ruleset: dict[str, Any]) -> None:
    _require(policy.get("schema_version") == 1, "unsupported release-governance schema")
    repository = policy.get("repository")
    _require(isinstance(repository, str) and repository.count("/") == 1, "repository must be owner/name")
    branch = policy.get("protected_branch")
    _require(isinstance(branch, str) and branch, "protected_branch is required")
    _require(policy.get("ruleset_enforcement") == "active", "ruleset must be active")
    _require(policy.get("require_pull_request") is True, "pull requests must be required")
    _require(policy.get("require_review_thread_resolution") is True, "review thread resolution must be required")
    _require(policy.get("require_branch_up_to_date") is True, "strict status checks must be required")
    _require(policy.get("block_force_push") is True, "force pushes must be blocked")
    _require(policy.get("block_branch_deletion") is True, "branch deletion must be blocked")
    _require(policy.get("allow_bypass") is False, "ruleset bypass must be disabled")

    required = policy.get("required_status_checks")
    _require(isinstance(required, list) and required, "required_status_checks must be non-empty")
    _require(all(isinstance(item, str) and item for item in required), "status check names must be strings")
    _require(len(required) == len(set(required)), "required_status_checks must be unique")

    _require(ruleset.get("name") == policy.get("ruleset_name"), "ruleset name drift")
    _require(ruleset.get("target") == "branch", "ruleset target must be branch")
    _require(ruleset.get("enforcement") == "active", "ruleset payload must be active")
    _require(ruleset.get("bypass_actors") == [], "ruleset bypass actors must be empty")
    refs = ruleset.get("conditions", {}).get("ref_name", {})
    _require(refs.get("include") == [f"refs/heads/{branch}"], "ruleset must target only the protected branch")

    rules = {item.get("type"): item for item in ruleset.get("rules", []) if isinstance(item, dict)}
    _require("deletion" in rules, "ruleset must block branch deletion")
    _require("non_fast_forward" in rules, "ruleset must block force pushes")
    pull_request = rules.get("pull_request", {}).get("parameters", {})
    _require(pull_request.get("required_review_thread_resolution") is True, "ruleset must require thread resolution")
    _require(
        pull_request.get("required_approving_review_count") == policy.get("required_approving_review_count"),
        "ruleset approval count does not match policy",
    )
    _require(pull_request.get("allowed_merge_methods") == policy.get("allowed_merge_methods"), "merge method drift")

    status_params = rules.get("required_status_checks", {}).get("parameters", {})
    _require(status_params.get("strict_required_status_checks_policy") is True, "status checks must require latest branch")
    actual_checks = status_params.get("required_status_checks", [])
    actual_contexts = [item.get("context") for item in actual_checks if isinstance(item, dict)]
    _require(actual_contexts == required, "required status check contexts drift")
    integration_id = policy.get("github_actions_integration_id")
    _require(
        all(item.get("integration_id") == integration_id for item in actual_checks),
        "required checks must be pinned to GitHub Actions integration",
    )


def _request(url: str, *, token: str | None = None, method: str = "GET", payload: dict[str, Any] | None = None,
             api_version: str = "2026-03-10") -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": api_version,
        "User-Agent": "cyberdudebivash-release-governance/1",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = response.read()
            return json.loads(data.decode("utf-8")) if data else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GovernanceError(f"GitHub API {method} {url} failed: HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise GovernanceError(f"GitHub API {method} {url} failed: {exc.reason}") from exc


def _repo_parts(repository: str) -> tuple[str, str]:
    owner, repo = repository.split("/", 1)
    return owner, repo


def list_repository_rulesets(repository: str, *, token: str | None, api_version: str) -> list[dict[str, Any]]:
    owner, repo = _repo_parts(repository)
    value = _request(f"{API_ROOT}/repos/{owner}/{repo}/rulesets", token=token, api_version=api_version)
    if not isinstance(value, list):
        raise GovernanceError("GitHub rulesets endpoint returned a non-list response")
    return [item for item in value if isinstance(item, dict)]


def verify_live(policy: dict[str, Any], *, token: str | None = None) -> dict[str, Any]:
    repository = policy["repository"]
    rulesets = list_repository_rulesets(repository, token=token, api_version=policy["api_version"])
    candidates = [item for item in rulesets if item.get("name") == policy["ruleset_name"]]
    _require(candidates, f"required ruleset {policy['ruleset_name']!r} is not installed")
    active = [item for item in candidates if item.get("enforcement") == "active"]
    _require(active, f"required ruleset {policy['ruleset_name']!r} is not active")
    return active[0]


def apply_ruleset(policy: dict[str, Any], ruleset: dict[str, Any], *, token: str) -> dict[str, Any]:
    _require(bool(token), "a GitHub token with Administration: write is required")
    repository = policy["repository"]
    owner, repo = _repo_parts(repository)
    api_version = policy["api_version"]
    existing = list_repository_rulesets(repository, token=token, api_version=api_version)
    match = next((item for item in existing if item.get("name") == policy["ruleset_name"]), None)
    if match:
        ruleset_id = match.get("id")
        _require(isinstance(ruleset_id, int), "existing ruleset is missing a numeric id")
        url = f"{API_ROOT}/repos/{owner}/{repo}/rulesets/{ruleset_id}"
        return _request(url, token=token, method="PUT", payload=ruleset, api_version=api_version)
    url = f"{API_ROOT}/repos/{owner}/{repo}/rulesets"
    return _request(url, token=token, method="POST", payload=ruleset, api_version=api_version)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", default=str(DEFAULT_POLICY))
    parser.add_argument("--ruleset", default=str(DEFAULT_RULESET))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="validate the checked-in governance contract")
    sub.add_parser("verify-live", help="fail unless the production ruleset is installed and active")
    apply_cmd = sub.add_parser("apply", help="create or update the production ruleset")
    apply_cmd.add_argument("--token-env", default="GH_ADMIN_TOKEN")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    policy = load_json(args.policy)
    ruleset = load_json(args.ruleset)
    try:
        validate_contract(policy, ruleset)
        if args.command == "validate":
            print("release-governance contract: PASS")
            return 0
        token = os.getenv(getattr(args, "token_env", "GH_ADMIN_TOKEN")) or os.getenv("GITHUB_TOKEN")
        if args.command == "verify-live":
            live = verify_live(policy, token=token)
            print(f"release-governance live ruleset: PASS id={live.get('id')} enforcement={live.get('enforcement')}")
            return 0
        if args.command == "apply":
            if not token:
                raise GovernanceError(
                    f"environment variable {args.token_env} must contain a fine-grained token with Administration: write"
                )
            result = apply_ruleset(policy, ruleset, token=token)
            print(f"release-governance ruleset applied: id={result.get('id')} enforcement={result.get('enforcement')}")
            verify_live(policy, token=token)
            return 0
        raise GovernanceError(f"unsupported command: {args.command}")
    except GovernanceError as exc:
        print(f"release-governance: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
