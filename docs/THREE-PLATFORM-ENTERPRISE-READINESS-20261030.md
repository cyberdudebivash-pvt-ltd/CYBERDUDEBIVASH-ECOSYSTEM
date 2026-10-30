# Three-Platform Enterprise Readiness and Commercial Release Gates

Status: PROPOSED — NOT A PRODUCTION CERTIFICATION
Date: 2026-10-30
Scope: SENTINEL APEX Threat Intel, AI Security Hub, SOC

## Governance
- Preserve current production functionality, data, URLs, entitlements, prices and existing customer commitments.
- No production writes or deploys from this plan without source access, baseline SHA, review, tests and rollback.
- Treat all advertised capabilities as unverified until evidence links identify a deployed build and passing test.
- Do not claim SOC 2 certification, 24/7 staffed SOC, guaranteed detection, regional data residency or SLA without substantiation.
- Each capability owner records implementation repository, commit SHA, deployment ID, test evidence, rollback owner and customer-facing documentation.

## Platform-specific P0 acceptance

### Threat Intel — intel.cyberdudebivash.com
1. Measure source-to-published freshness with timestamps; reject stale or empty publication and preserve last-known-good feed.
2. Validate schema, deduplication, IOC provenance, CVE/CWE/KEV enrichment, confidence and false-positive controls.
3. Test API auth, rate limits, pagination, versioning, export consistency and customer entitlements.
4. Confirm frontend dashboard, map and API consume same published version; monitor drift and alert.
5. Test R2/KV recovery, publisher retries, idempotence and rollback.

### AI Security Hub — cyberdudebivash.in
1. Verify auth, password-reset/session revocation, MFA where advertised, tenant isolation and horizontal authorization denial cases.
2. Resolve and independently retest outstanding researcher disclosures before closing tickets or issuing recognition.
3. Verify authorized assessment scope, input validation, safe execution, result integrity, report generation and evidence retention.
4. Validate product catalog, price consistency, payment/invoice path, account provisioning, entitlement revocation and cancellation.
5. Test end-to-end demo, signup, onboarding, support and incident reporting on desktop and mobile.

### SOC — soc.cyberdudebivash.in
1. Validate authenticated event ingestion, tenant isolation, deduplication, timestamp handling, backpressure and replay.
2. Test alert-to-case lifecycle, evidence chain, analyst actions, RBAC and immutable audit events.
3. Verify integrations, connector health, detection rules, correlation and suppression using labeled test events.
4. Exercise failure recovery, retention, backup/restore, monitoring and explicit operational coverage boundaries.
5. Verify customer dashboard branding, accessibility, response workflows and accurate service-level claims.

## Shared release evidence checklist
- [ ] Source repository and immutable baseline SHA identified
- [ ] Product capability inventory mapped to deployed endpoints/screens
- [ ] Critical authorization and isolation negative tests pass
- [ ] CI: unit, integration, end-to-end, SAST, dependency and secret scanning pass
- [ ] Load/latency/error budget evidence attached
- [ ] Backup restoration and rollback tested
- [ ] Privacy, retention, DPA and contractual claims reviewed
- [ ] Published pricing and entitlements reconciled
- [ ] New customer purchase-to-delivery journey verified
- [ ] Independent release approver signs off

## Commercial offer design (proposal; not published prices)
- Threat Intel: self-service intelligence subscription, team API tier, enterprise feed and analyst services.
- AI Security Hub: assessment credits, team security workspace, enterprise deployment and governance services.
- SOC: SOC readiness assessment, managed platform tier, enterprise integration and response support.
- Quote enterprise pricing based on scope, supported coverage, evidence, cost-to-serve and contractual commitments.
- Do not change existing price lists or promise unsupported SLAs until commercial approval.

## Scorecard
For each platform track: baseline SHA; last successful deployment; release gate pass/fail; P0 count; freshness/availability SLO; p95 latency; tenant isolation test status; demo-to-qualified-lead rate; lead-to-paid conversion; verified revenue.

## Deployment decision
Default HOLD if any P0 fails or is unverified. Use controlled staging/canary, explicit rollback trigger and customer communication before production rollout.
