# Global Growth Intelligence & Attribution Engine

## Purpose

The Growth Attribution Engine closes the operating loop between campaign creation and measurable downstream action without turning the public ecosystem repository into a customer-tracking database.

It provides:

- deterministic campaign identifiers;
- governed UTM generation;
- canonical destination enforcement;
- campaign lifecycle controls;
- privacy-safe aggregate performance validation;
- funnel-rate calculation;
- channel scorecards;
- evidence-bounded recommendations;
- GitHub Actions scorecard automation;
- a future-compatible contract for private analytics integrations.

## Operating principle

Attribution is evidence, not causality.

A tracked click, lead or conversion can support an attribution claim when the measurement contract is satisfied. It does not prove that the campaign alone caused the outcome.

## Campaign identity

Campaign IDs are deterministic for the tuple:

`date + objective + platform`

Example format:

`cdb-YYYYMMDD-objective-platform-8hex`

Repeated generation for the same tuple produces the same ID. This supports idempotency and duplicate suppression.

## UTM governance

Every enabled channel receives a URL generated from the canonical ecosystem destination.

Required parameters:

- `utm_source`
- `utm_medium`
- `utm_campaign`

Optional parameters:

- `utm_content`
- `utm_term`

`utm_campaign` is always the campaign ID and is the attribution join key.

The engine rejects destinations outside the governed CYBERDUDEBIVASH® platform registry.

## Campaign lifecycle

Allowed states:

`planned -> approved -> active -> measuring -> completed -> archived`

Additional controlled paths:

- `planned -> rejected -> archived`
- `approved -> rejected -> archived`
- `active -> completed`

Invalid transitions fail closed.

## Performance data contract

Performance input is aggregate-only.

Required top-level fields:

- `schema_version`
- `campaign_id`
- `window_start`
- `window_end`
- `channel`
- `platform`
- `metrics`

Required aggregate metrics:

- impressions
- clicks
- engaged visits
- CTA actions
- leads
- conversions

The runtime validator rejects:

- personal identifiers;
- credentials or secrets;
- unsupported fields;
- disabled or unknown channels;
- invalid dates;
- negative or non-integer metrics;
- impossible click/engagement relationships.

The machine-readable contract is documented in `schemas/campaign-performance.schema.json`.

## Privacy boundary

This repository is public.

Do not commit private analytics exports, customer identifiers, email addresses, IP addresses, session identifiers, device identifiers, payment data, credentials, or confidential commercial telemetry.

`data/performance/` is only for aggregate metrics that have been explicitly approved for public repository use.

Private performance data should be processed by the same engine in a private CI/runtime environment and only the approved aggregate result should be surfaced.

## KPI model

The scorecard calculates:

- click-through rate;
- engaged visit rate;
- CTA rate;
- lead rate;
- conversion rate;
- a bounded 0–100 performance index.

The performance index is a policy-controlled target-attainment score, not an industry benchmark or claim of marketing effectiveness.

Configured targets and weights live in `config/growth-policy.json`.

## Recommendations

Recommendations are deliberately bounded.

The engine may:

- identify a channel with materially stronger observed performance when minimum sample rules are met;
- identify KPIs below configured internal targets;
- state that the sample is insufficient.

The engine may not:

- invent reasons for performance;
- infer customer identity;
- claim causal impact from correlation;
- recommend budget reallocation from insufficient data;
- publish results externally without approval.

## Commands

Create a governed tracking bundle:

```bash
python scripts/growth_attribution.py campaign \
  --date 2026-08-17 \
  --objective authority \
  --platform all \
  --output reports/campaign-tracking.json
```

Transition a campaign:

```bash
python scripts/growth_attribution.py transition \
  --record reports/campaign-tracking.json \
  --to-state approved \
  --output reports/campaign-tracking-approved.json
```

Validate performance records:

```bash
python scripts/growth_attribution.py validate-performance \
  --input /secure/path/performance.jsonl
```

Generate a scorecard:

```bash
python scripts/growth_attribution.py scorecard \
  --input /secure/path/performance.jsonl \
  --campaign-id cdb-20260817-authority-all-xxxxxxxx \
  --output-json reports/growth-scorecard.json \
  --output-markdown reports/growth-scorecard.md
```

## GitHub automation

### Weekly Global Campaign Engine

The weekly campaign workflow now creates:

1. a campaign brief;
2. a deterministic campaign ID;
3. a governed tracking bundle;
4. channel-specific tracked URLs;
5. an idempotent analyst-review issue.

### Growth Attribution Scorecard

The scorecard workflow processes only public-approved aggregate files under `data/performance/`.

If no approved data exists, it emits a zero-state report instead of inventing results.

## Future private integrations

Approved analytics connectors can later write the same aggregate contract from:

- first-party web analytics;
- LinkedIn;
- X;
- YouTube;
- email;
- product telemetry;
- CRM lead attribution.

Those integrations must use scoped credentials, private storage, data minimization, retention controls, audit logs, and explicit publication policy.
