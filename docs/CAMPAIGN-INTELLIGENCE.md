# Campaign Intelligence Engine v2

## Objective

Turn trusted CYBERDUDEBIVASH® ecosystem signals into ranked, evidence-backed PR and digital-marketing opportunities without allowing automation to publish unsupported claims.

## Control flow

1. **Collect** from allowlisted first-party JSON endpoints and approved public GitHub release feeds.
2. **Normalize** heterogeneous source payloads into one signal contract.
3. **Score** each signal from 0–5 across strategic alignment, audience urgency, evidence strength, commercial relevance, cross-sell potential, and timeliness.
4. **Gate** on evidence, total score, and freshness.
5. **Fingerprint** each signal deterministically with SHA-256.
6. **Deduplicate** against existing GitHub issues.
7. **Open** only the highest-ranked eligible opportunities, capped per run.
8. **Require analyst review** before campaign generation or any external publication.

## Trust model

Source trust is explicit and version-controlled in `config/intelligence-sources.json`.

- `5` — first-party GitHub release record or equivalent authoritative release evidence.
- `4` — first-party production intelligence/API source confirmed by the ecosystem owner.
- `3` — approved source that is useful but requires stronger contextual verification.
- `1–2` — must never pass the default evidence gate.

The production policy in `config/intelligence-policy.json` requires evidence ≥3/5 and total score ≥18/30.

## Supported source types

### JSON

HTTPS-only JSON from an allowlisted hostname. The collector uses bounded response sizes, timeouts, and a fixed user-agent. It handles common list/data/result wrappers and maps flexible title/date/summary/link fields into the normalized schema.

### GitHub releases

Approved repositories under `cyberdudebivash-pvt-ltd/*`. The workflow passes the repository-scoped GitHub token to GitHub API requests, increasing rate-limit reliability without storing another credential.

## Normalized signal contract

Each signal carries:

- source ID and type;
- platform and purpose;
- trust level;
- external ID when available;
- title and bounded summary;
- canonical evidence URL;
- publication time when supplied;
- source URL;
- deterministic fingerprint;
- six scoring dimensions;
- total score;
- eligibility and issue-selection flags.

## Scoring

| Dimension | Range | Meaning |
|---|---:|---|
| Strategic alignment | 0–5 | Fit with a governed ecosystem platform |
| Audience urgency | 0–5 | Security or market urgency signaled by the evidence |
| Evidence strength | 0–5 | Source authority/trust |
| Commercial relevance | 0–5 | Connection to enterprise adoption or demand |
| Cross-sell potential | 0–5 | Ability to connect relevant ecosystem capabilities |
| Timeliness | 0–5 | Recency of the source signal |

Scoring is deterministic prioritization support. It is not a truth engine, legal approval, security validation, or publication authorization.

## Failure behavior

- A single source failure is recorded and does not stop healthy sources from being processed.
- If **all** trusted sources fail, the workflow uploads whatever diagnostic report exists and then fails.
- Weak evidence never becomes an eligible issue.
- Signals older than the configured maximum age fail the freshness gate.
- Each run can open at most the configured number of issues.
- Existing signal fingerprints are not reopened.

## Publication boundary

The workflow creates GitHub issues only. It does not post to LinkedIn, X, YouTube, blogs, email, messaging systems, or customer channels.

Every generated issue contains an analyst checklist requiring:

- source verification;
- fact/source-claim/analysis/inference separation;
- product claim verification;
- one audience and one objective;
- canonical CTA selection;
- sensitive-data review;
- channel-specific approval.

## Schedule

The engine runs twice daily at `02:23 UTC` and `14:23 UTC`, and can also be triggered manually.

## Operations

Run locally:

```bash
python scripts/validate_intelligence_config.py
python scripts/intelligence_engine.py \
  --output-json reports/opportunities.json \
  --output-markdown reports/campaign-intelligence.md
python -m unittest discover -s tests -v
```

## Expansion rules

Add new automated source adapters only when all of the following are true:

1. the source has a stable machine-readable contract;
2. provenance can be preserved;
3. authentication can use scoped secrets or GitHub-native credentials;
4. response size/timeouts can be bounded;
5. source failure can be isolated;
6. deduplication is deterministic;
7. the new source does not weaken the publication gate.

Future adapters may include approved product-release feeds, Academy releases, TrustX releases, SEO opportunity feeds, channel performance imports, and analyst-approved market intelligence.
