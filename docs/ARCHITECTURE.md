# Architecture

## Control plane

`config/ecosystem.json` is the canonical platform registry. `config/brand.json` defines brand and publication constraints. The scripts consume these inputs to produce auditable health and campaign outputs.

## Agent layers

1. **Registry layer** — canonical products, URLs, categories, audiences and positioning.
2. **Observability layer** — external HTTP health audit and platform availability report.
3. **Campaign layer** — deterministic brief generation for a selected product or the full ecosystem.
4. **Governance layer** — review gates for claims, security, brand, privacy and legal/reputational risk.
5. **Workflow layer** — GitHub Actions creates recurring artifacts and campaign issues.
6. **Distribution layer** — optional future connectors for approved social, email, CRM and analytics APIs.

## Security model

- no secrets in repository content;
- external publishing disabled by default;
- least-privilege GitHub Actions permissions;
- generated issues are drafts/operations artifacts, not automatic public claims;
- platform health requests use bounded timeouts and no authentication;
- all campaign claims require evidence review.
