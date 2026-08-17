from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
from common import ROOT, load_json

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


def render(platforms: list[dict], objective: str) -> str:
    generated = dt.datetime.now(dt.timezone.utc).date().isoformat()
    names = ", ".join(p["name"] for p in platforms)
    audiences = sorted({aud for p in platforms for aud in p["audiences"]})
    primary_url = "https://www.cyberdudebivash.com/" if len(platforms) > 1 else platforms[0]["url"]
    platform_lines = "\n".join(f"- **{p['name']}** — {p['positioning']} — {p['url']}" for p in platforms)

    return f"""# Global Campaign Brief — {generated}

## Objective
{OBJECTIVES[objective]}

## Scope
{names}

## Primary audiences
{', '.join(audiences)}

## Core narrative
CYBERDUDEBIVASH® connects specialized security capabilities into a coherent ecosystem spanning AI security, threat intelligence, enterprise defense, trust/governance, practitioner tooling and education. The campaign must lead with a specific evidence-backed customer or practitioner outcome rather than generic claims.

## Platform proof points to validate before publishing
{platform_lines}

## Flagship asset
Publish or select one owned CYBERDUDEBIVASH® page containing the strongest evidence, product experience, report, demonstration or educational value for this campaign.

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
Primary destination: {primary_url}

Use one CTA per asset. Do not dilute conversion intent with a long list of unrelated links.

## Mandatory review gates
- [ ] All product and security claims verified against current production evidence.
- [ ] No fabricated customer, certification, partnership, revenue or analyst endorsement.
- [ ] No secrets, customer data or sensitive vulnerability details.
- [ ] Brand names and canonical URLs verified.
- [ ] Security-intelligence claims distinguish fact, source claim, analysis and inference.
- [ ] CTA and campaign tracking parameters validated.

## KPIs
- qualified click-through rate;
- engaged visits to owned CYBERDUDEBIVASH® properties;
- cross-platform exploration;
- enterprise/contact/tool/course intent;
- earned mentions, citations and saves by target audiences;
- follow-on questions or opportunities generated.

## Post-campaign review
Record results at 24 hours, 72 hours and 7 days. Capture what message, channel, audience and asset produced the highest-quality downstream action, then convert that learning into the next campaign issue.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", default="all")
    parser.add_argument("--objective", choices=sorted(OBJECTIVES), default="authority")
    parser.add_argument("--output", default="reports/campaign-brief.md")
    args = parser.parse_args()
    data = load_json("config/ecosystem.json")
    platforms = select_platforms(data, args.platform)
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(platforms, args.objective), encoding="utf-8")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
