# SEO Opportunity Intelligence

## Purpose

The SEO Opportunity Engine converts governed CYBERDUDEBIVASH® strategic topic hypotheses into a reproducible, evidence-aware prioritization backlog.

It is designed to avoid a common failure mode in automated SEO systems: inventing keyword volume, ranking position, competition, or market demand when no trusted search-data source is connected.

## Inputs

- `config/seo-policy.json` — scoring, evidence, confidence, and recommendation policy.
- `config/seo-topics.json` — governed topic hypotheses mapped to canonical ecosystem platforms.
- `config/ecosystem.json` — valid platform IDs and destinations.

## Internal signals

Each topic is scored 0–5 on:

- strategic fit;
- commercial intent;
- authority fit;
- landing readiness;
- content gap.

These values are **internal editorial planning inputs**, not external market facts.

## External evidence

A topic may carry either:

`status: none`

or a verified external evidence block from an approved provider.

Verified evidence contains normalized 0–5:

- demand score;
- competition-opportunity score.

The engine does not accept market metrics under an unverified evidence status.

Approved providers are governed by policy. The initial registry does not invent external evidence; all seed topics are deliberately `internal-only`.

## Decision score

Internal score:

`Σ(signal / 5 × internal_weight) × 100`

When verified external evidence exists, internal and external scores are blended using policy weights.

A confidence multiplier is then applied:

- `internal-only`: 0.85
- `verified-external`: 1.00

This produces an internal **decision score**, not an industry benchmark.

## Ranking and demand claims

Ranking or demand claims are not authorized by internal-only evidence.

The report explicitly distinguishes:

- internal editorial opportunity;
- verified external search evidence.

## Internal-link recommendations

Recommended topics include target platform/path plus governed source platforms from which contextual internal links should be evaluated.

These are recommendations, not automatic website mutations.

## Automation

The public **SEO Opportunity Intelligence** GitHub workflow may render reports from the public governed topic registry because those inputs contain no private analytics or confidential search-console exports.

Private Search Console, Bing Webmaster, or commercial SEO-provider exports must be normalized outside public GitHub Actions before any intentionally public evidence is committed.
