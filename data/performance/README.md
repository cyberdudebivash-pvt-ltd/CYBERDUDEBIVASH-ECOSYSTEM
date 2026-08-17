# Public-Approved Performance Data

This directory is intentionally empty by default.

Only privacy-safe aggregate campaign performance that is explicitly approved for publication in a public GitHub repository may be committed here.

Do not commit:

- personal identifiers;
- customer records;
- raw analytics exports;
- IP/session/device identifiers;
- credentials or tokens;
- payment information;
- confidential pipeline or revenue data;
- commercially sensitive metrics not approved for public disclosure.

Use `schemas/campaign-performance.schema.json` and `scripts/growth_attribution.py validate-performance` before committing any record.

For confidential analytics, run the engine against a private file or private CI store instead of placing the data in this directory.
