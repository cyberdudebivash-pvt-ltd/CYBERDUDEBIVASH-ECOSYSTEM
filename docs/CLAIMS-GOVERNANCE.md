# Claims Governance

## Objective

Prevent unsupported legal, compliance, commercial-secret and market-leadership claims from entering public campaign or PR content.

The production decision model is **deny by default**. A claim is publishable only when `config/claims-governance.json` marks it `approved` and supplies the exact approved public wording plus the required evidence metadata.

## Status model

| Status | Publication behavior |
|---|---|
| `approved` | Exact approved wording may be used while the evidence review remains current. |
| `hold` | Do not publish, infer or paraphrase the claim. |
| `prohibited` | Retired from public use until a new evidence-backed approval changes the policy. |
| `private-only` | May exist only in scoped private configuration or secrets; never publish or commit the identifier. |

## Current production decisions

- Legal entity wording: `hold`.
- GST registration claim: `hold`.
- MSME/Udyam registration claim: `hold`.
- Startup India recognition claim: `hold`.
- Payment-provider plan identifiers: `private-only`.
- India-first AI-native market-leadership claim: `prohibited`.
- Public location wording: `approved` as **Odisha, India**.

A `hold` state does not assert that a fact is false. It means the public control plane does not yet contain sufficient authoritative evidence metadata to publish the claim safely.

## Evidence activation workflow

For a legal, tax, government-recognition, regulatory, certification or market-leadership claim:

1. Review the authoritative source outside this public repository.
2. Do not copy registration numbers, payment plan identifiers, PAN values, GSTIN values, Udyam registration numbers, credentials or private evidence into GitHub.
3. Record only a public-safe evidence reference, evidence type and evidence owner.
4. Add the exact approved public wording.
5. Record approval and review-due dates.
6. Change status to `approved` through a pull request.
7. Require Repository Quality and CodeQL to pass on the exact PR head before merge.

Legal/compliance categories cannot become `approved` with owner assertion alone; the validator requires an authoritative evidence type.

## Enforcement layers

`python scripts/validate_claims_governance.py` performs:

- claims-policy structural validation;
- approval-expiry enforcement;
- authoritative-evidence enforcement;
- prohibited-superlative detection;
- unapproved legal/compliance self-claim detection;
- repository-wide sensitive-identifier scanning for tracked text files.

`python scripts/validate_public_directory.py` additionally rejects sensitive identifier values inside the public directory.

`scripts/generate_campaign.py` validates every generated campaign brief before writing it. A sensitive identifier, prohibited market claim or unapproved detected legal/compliance claim raises an error and stops generation.

## Sensitive-data boundary

The public repository may contain public business contact information intentionally listed in `config/public-directory.json`. It must not contain private registration identifiers, payment-provider plan IDs, live credentials, private evidence documents or customer-private information.

## Emergency rule

If evidence is missing, contradictory, expired or cannot be safely referenced, leave the claim on `hold`. Publication pressure never overrides the evidence gate.
