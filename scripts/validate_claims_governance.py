from __future__ import annotations

from claims_governance import load_policy, scan_repository, validate_policy


def validate() -> list[str]:
    policy = load_policy()
    errors = validate_policy(policy)
    if errors:
        return errors
    return scan_repository(policy)


if __name__ == "__main__":
    failures = validate()
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}")
        raise SystemExit(1)
    print("Claims governance validation passed.")
