# Editorial Portfolio & Capacity Control

## Purpose

This control plane prevents the Weekly Global Campaign Engine from repeatedly promoting the same platform, repeating the same campaign objective, or creating more analyst-review campaigns than the configured operating capacity.

It is a planning and governance layer only. It does not publish externally.

## Canonical policy

`config/editorial-policy.json` is the machine-readable source of truth for:

- campaign history lookback;
- ISO-week and rolling-window capacity;
- minimum spacing between campaigns;
- same-platform cooldown;
- per-platform lookback caps;
- coverage targets;
- objective lookback and repetition caps;
- platform strategic priorities;
- objective strategic priorities;
- approved objectives by platform;
- whether legacy `all` campaigns count as touching every platform;
- whether manual all-platform campaigns are allowed.

Configuration changes require pull-request review and must pass `scripts/validate_editorial_config.py`.

## Planner inputs

`scripts/portfolio_planner.py` consumes:

1. `config/ecosystem.json`;
2. `config/editorial-policy.json`;
3. public GitHub campaign-operations issue history;
4. an explicit UTC planning date;
5. optional manual platform/objective requests.

Only issue titles using the governed format are interpreted as campaign history:

`Global Campaign: <campaign-id> / <objective> / <platform>`

Unrelated issues are ignored. A title that uses the reserved `Global Campaign:` prefix but does not match the contract fails closed.

## Global capacity gates

A campaign is not planned when any of these conditions is true:

- the configured ISO-week capacity is already exhausted;
- the configured rolling-window capacity is exhausted;
- the minimum global spacing since the most recent campaign is not satisfied.

A capacity block is a successful no-op, not a workflow failure. The planning artifact records the reason.

## Platform eligibility

For each governed ecosystem platform, the planner calculates:

- campaigns inside the history lookback;
- campaigns inside the coverage window;
- coverage debt;
- most recent campaign date;
- days since the platform was last touched;
- configured strategic priority.

A platform is excluded when:

- its cooldown has not expired; or
- its per-platform lookback cap has been reached.

Legacy `all` campaigns count as touching every platform when the policy flag is enabled.

Eligible platforms are ranked deterministically:

1. higher coverage debt;
2. fewer campaigns in the history lookback;
3. longer time since last campaign;
4. higher configured strategic priority;
5. stable lexical platform-ID tie-break.

There is no random selection and no model-generated scheduling decision.

## Objective selection

Each platform has an explicit allowlist of objectives.

Eligible objectives are ranked deterministically:

1. fewer uses inside the objective lookback;
2. avoid immediately repeating the most recent objective;
3. higher configured objective priority;
4. stable lexical objective-ID tie-break.

Objectives that have reached the configured repetition cap are excluded.

## Manual workflow requests

`workflow_dispatch` may request a specific platform and/or objective.

Manual requests remain governed:

- unknown platforms/objectives fail closed;
- platform cooldown and platform lookback caps still apply;
- objective/platform compatibility is enforced;
- objective repetition caps still apply when configured;
- `all` is disabled unless the policy explicitly enables it;
- global capacity and spacing always apply.

There is no hidden force-publish switch.

## Planning output

The planner writes `reports/editorial-plan.json`.

The plan contains:

- `status`;
- selected platform/objective when planned;
- requested overrides;
- ISO-week and rolling capacity state;
- history record count and warnings;
- deterministic selection reasons;
- ranked platform candidates;
- excluded platforms and exclusion reasons;
- ranked objective candidates;
- excluded objectives and exclusion reasons.

Governed statuses:

- `planned`;
- `capacity-exhausted`;
- `no-eligible-platform`;
- `no-eligible-objective`;
- `blocked`.

The output contract is documented by `schemas/editorial-plan.schema.json`.

## Weekly workflow behavior

Scheduled runs use `auto` for both platform and objective.

The workflow:

1. validates claims, growth and editorial governance;
2. collects public campaign issue metadata;
3. creates the deterministic portfolio plan;
4. uploads the planning decision;
5. stops cleanly when the status is not `planned`;
6. otherwise generates the campaign brief and tracking bundle;
7. creates an idempotent analyst-review issue containing the planning rationale;
8. does not publish to external channels.

## Safety properties

- no credentials;
- no private analytics inputs;
- no person-level telemetry;
- no external social publishing;
- no probabilistic or model-generated scheduling;
- no manual bypass of capacity;
- no silent malformed-history acceptance;
- no duplicate campaign issue for the same deterministic campaign ID.

## Local validation

```bash
python scripts/validate_editorial_config.py

python scripts/portfolio_planner.py \
  --history reports/campaign-history.json \
  --as-of 2026-08-17 \
  --requested-platform auto \
  --requested-objective auto \
  --output-json reports/editorial-plan.json

python -m unittest tests.test_portfolio_planner -v
```
