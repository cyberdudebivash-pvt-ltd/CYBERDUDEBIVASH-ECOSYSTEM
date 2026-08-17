from __future__ import annotations

import argparse
import datetime as dt
import socket
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
from common import ROOT, load_json

USER_AGENT = "CYBERDUDEBIVASH-Ecosystem-Health/1.0"


def probe(url: str, timeout: float = 12.0) -> dict:
    request = urllib.request.Request(url, method="GET", headers={"User-Agent": USER_AGENT})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
            status = int(response.getcode())
            final_url = response.geturl()
            elapsed_ms = round((time.monotonic() - started) * 1000)
            return {"ok": 200 <= status < 400, "status": status, "elapsed_ms": elapsed_ms, "final_url": final_url, "error": ""}
    except urllib.error.HTTPError as exc:
        elapsed_ms = round((time.monotonic() - started) * 1000)
        return {"ok": False, "status": int(exc.code), "elapsed_ms": elapsed_ms, "final_url": url, "error": f"HTTP {exc.code}"}
    except (urllib.error.URLError, TimeoutError, socket.timeout, ssl.SSLError) as exc:
        elapsed_ms = round((time.monotonic() - started) * 1000)
        return {"ok": False, "status": 0, "elapsed_ms": elapsed_ms, "final_url": url, "error": str(exc)[:200]}


def render(results: list[tuple[dict, dict]]) -> str:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    lines = [
        "# CYBERDUDEBIVASH® Ecosystem Platform Health",
        "",
        f"Generated: `{now}`",
        "",
        "| Platform | Status | HTTP | Latency | Canonical URL |",
        "|---|---:|---:|---:|---|",
    ]
    for platform, result in results:
        state = "UP" if result["ok"] else "DEGRADED"
        http = result["status"] or "n/a"
        lines.append(f"| {platform['name']} | {state} | {http} | {result['elapsed_ms']} ms | {platform['url']} |")
    failures = [(p, r) for p, r in results if not r["ok"]]
    lines.extend(["", "## Result", ""])
    if failures:
        lines.append(f"**{len(failures)} platform(s) require review.**")
        for platform, result in failures:
            lines.append(f"- **{platform['name']}** — {result['error'] or 'unexpected response'}")
    else:
        lines.append("All registered platform entry points responded successfully.")
    lines.extend(["", "> Availability checks validate public HTTP reachability only; they do not prove application-level correctness or security.", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="reports/platform-health.md")
    args = parser.parse_args()
    data = load_json("config/ecosystem.json")
    results = [(platform, probe(platform["url"])) for platform in data["platforms"]]
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(results), encoding="utf-8")
    degraded = sum(1 for _, result in results if not result["ok"])
    print(f"Wrote {output}; degraded={degraded}")
    return 1 if degraded else 0


if __name__ == "__main__":
    raise SystemExit(main())
