# Private First-Party Analytics

## Purpose

Phase 2C adds a privacy-preserving analytics runtime for measuring owned CYBERDUDEBIVASH® properties without turning this public repository or its GitHub Actions history into an analytics database.

## Security boundary

The analytics runtime is **private-only**.

- Runtime input files committed to this repository are forbidden.
- Repo-local analytics files must live under `private/`, which is gitignored.
- Derived private scorecards inside the repo must also stay under `private/`.
- External secure paths are allowed for local/private runners.
- Public GitHub Actions do not ingest, transform, upload, or publish private analytics.
- API-backed providers remain disabled until a private runner and scoped credential boundary are provisioned.

This is an architectural control, not a documentation preference.

## Normalized aggregate contracts

Two aggregate record types are supported.

### Funnel record

A funnel record contains:

- canonical owned property host;
- platform ID;
- date window;
- campaign ID (`organic`, `direct`, or governed campaign IDs are valid safe identifiers);
- acquisition channel;
- landing path without query-string or fragment data;
- aggregate session, engagement, CTA, lead, and conversion counts.

The validator rejects impossible funnel relationships:

`conversions <= leads <= cta_events <= engaged_sessions <= sessions`

### Assist record

An assist record models an **aggregate cross-platform edge**:

`from_platform -> to_platform`

with only:

- aggregate journeys;
- aggregate assisted conversions.

No session IDs, visitor IDs, cookies, fingerprints, device IDs, email addresses, IP addresses, or other person-level join keys are allowed.

## Provider model

`config/analytics-policy.json` currently enables only `manual-aggregate` file ingestion.

The following provider adapters are registered but disabled:

- Cloudflare Web Analytics API;
- GA4 Data API.

They must remain disabled until their credentials and execution environment are isolated from this public repository.

## CLI

Validate a private aggregate file:

```bash
python scripts/private_analytics.py validate \
  --input private/analytics/weekly.jsonl
```

Generate a private scorecard:

```bash
python scripts/private_analytics.py scorecard \
  --input private/analytics/weekly.jsonl \
  --output-json private/reports/private-analytics-scorecard.json \
  --output-markdown private/reports/private-analytics-scorecard.md
```

An absolute path outside the repository is also valid when it points to a secured runtime location.

## Governance

Analytics output remains attribution evidence, not causality proof. Any later public disclosure of aggregate performance requires an explicit publication review separate from analytics processing.
