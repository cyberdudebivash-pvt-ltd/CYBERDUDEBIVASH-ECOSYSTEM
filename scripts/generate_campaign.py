from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from common import ROOT, load_json
from growth_attribution import create_campaign_bundle, validate_campaign_record

OBJECTIVES = {
    "authority": "Strengthen global technical and enterprise authority with evidence-led ecosystem positioning.",
    "demand": "Create qualified commercial interest and move target audiences toward an owned conversion point.",
    "adoption": "Increase meaningful platform exploration and cross-ecosystem adoption.",
    "launch": "Coordinate a high-signal product, feature, research or platform launch.",
    "education": "Teach a valuable security concept while connecting it to relevant ecosystem capabilities.",
    "trust": "Increase confidence through transparent security, governance, provenance and responsible claims."
}


def select_platforms(data: dict, requested: str) -> list[dict]:
    if requested == "all":
        return data["platforms"]
    matches = [item for item in data["platforms"] if item["id"] == requested]
    if not matches:
        valid = ", ".join(["all"] + [p["id"] for p in data["platforms"]])
        raise SystemExit(f"Unknown platform '{requested}'. Valid values: {valid}")
    return matches


def render(
    platforms: list[dict],
    objective: str,
    tracking_bundle: dict | None = None,
) -> str:
    generated = dt.datetime.now(dt.timezone.utc).date().isoformat()
    names = ", ".join(p["name"] for p in platforms)
    audiences = sorted({aud for p in platforms for aud in p.get("audiences", [])})
    primary_url = "https://www.cyberdudebivash.com/" if len(platforms) > 1 else platforms[0]["url"]
    platform_lines = "\n".join(
        f"- **{p['name']}** — {p.get('positioning', 'Governed ecosystem platform.')} — {p['url']}"
        for p in platforms
    )

    tracking_section = ""
    cta_url = primary_url
    if tracking_bundle:
        cta_url = tracking_bundle["destination"]
        tracking_lines = "\n".join(
            f"- **{channel}**: {url}"
            for channel, url in tracking_bundle["tracking_urls"].items()
        )
        tracking_section = f"""
## Campaign identity and attribution
Campaign ID: `{tracking_bundle['campaign_id']}`  
Lifecycle state: `{tracking_bundle['state']}`  
Canonical destination: {tracking_bundle['destination']}

### Governed channel URLs
{tracking_lines}

Use the channel-specific URL for the matching distribution channel. Do not alter `utm_campaign`; it is the attribution join key. UTM parameters measure attributable traffic, not causality.
"""

    audience_text = ", ".join(audiences) if audiences else "Define one primary audience before publication."

    return f"""# Global Campaign Brief — {generated}

## Objective
{OBJECTIVES[objective]}

## Scope
{names}

## Primary audiences
{audience_text}

## Core narrative
CYBERDUDEBIVASH® connects specialized security capabilities into a coherent ecosystem spanning AI security, threat intelligence, enterprise defense, trust/governance, practitioner tooling and education. The campaign must lead with a specific evidence-backed customer or practitioner outcome rather than generic claims.

## Platform proof points to validate before publishing
{platform_lines}

## Flagship asset
Publish or select one owned CYBERDUDEBIVASH® page containing the strongest evidence, product experience, report, demonstration or educational value for this campaign.
{tracking_section}
## Distribution sequence
1. **Owned web / blog** — canonical flagship asset and source of truth.
2. **LinkedIn** — executive + practitioner narrative with one primary CTA.
3. **X** — concise technical hook, evidence and canonical URL.
4. **YouTube / short video** — visual explanation or product proof with persistent brand/URL visibility.
5. **Community / partner outreach** — targeted distribution only where the content is relevant.
6. **Internal ecosystem cross-linking** — contextual links from related CYBERDUDEBIVASH® properties.

## Content derivatives
- executive post: business risk / outcome / proof / CTA;
- technical post: architecture, intelligence or practitioner value;
- short-form video: one concept, one visual story, one CTA;
- carousel/banner: high-clarity headline + proof point + canonical URL;
- FAQ/objection asset: answer the strongest buyer or practitioner question.

## CTA
Canonical destination: {cta_url}

Use one CTA per asset. When a tracking bundle exists, use the governed URL assigned to the distribution channel instead of manually composing UTM parameters.

## Mandatory review gates
- [ ] All product and security claims verified against current production evidence.
- [ ] No fabricated customer, certification, partnership, revenue or analyst endorsement.
- [ ] No secrets, customer data or sensitive vulnerability details.
- [ ] Brand names and canonical URLs verified.
- [ ] Security-intelligence claims distinguish fact, source claim, analysis and inference.
- [ ] Campaign ID and channel-specific tracking URL validated.
- [ ] CTA and campaign tracking parameters validated.

## KPIs
- qualified click-through rate;
- engaged visits to owned CYBERDUDEBIVASH® properties;
- CTA actions and qualified lead intent;
- cross-platform exploration;
- enterprise/contact/tool/course/API intent;
- earned mentions, citations and saves by target audiences;
- follow-on questions or opportunities generated.

## Post-campaign review
Record aggregate results at 24 hours, 72 hours and 7 days where data is available. Use the Growth Attribution Engine to compare message, channel, audience and downstream action. Do not store personal or customer-private telemetry in this public repository.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", default="all")
    parser.add_argument("--objective", choices=sorted(OBJECTIVES), default="authority")
    parser.add_argument("--output", default="reports/campaign-brief.md")
    parser.add_argument("--tracking-output", default="")
    parser.add_argument("--campaign-date", default="")
    parser.add_argument("--content", default="primary")
    args = parser.parse_args()

    ecosystem = load_json("config/ecosystem.json")
    platforms = select_platforms(ecosystem, args.platform)
    tracking_bundle = None
    if args.tracking_output:
        policy = load_json("config/growth-policy.json")
        channels = load_json("config/channel-taxonomy.json")
        campaign_date = args.campaign_date or dt.datetime.now(dt.timezone.utc).date().isoformat()
        tracking_bundle = create_campaign_bundle(
            ecosystem,
            channels,
            policy,
            campaign_date=campaign_date,
            objective=args.objective,
            platform=args.platform,
            content=args.content,
        )
        validate_campaign_record(tracking_bundle, policy, ecosystem)
        tracking_path = Path(args.tracking_output)
        if not tracking_path.is_absolute():
            tracking_path = ROOT / tracking_path
        tracking_path.parent.mkdir(parents=True, exist_ok=True)
        tracking_path.write_text(
            json.dumps(tracking_bundle, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {tracking_path}")

    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(platforms, args.objective, tracking_bundle), encoding="utf-8")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
