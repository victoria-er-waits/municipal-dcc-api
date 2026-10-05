#!/usr/bin/env python3
"""Minimal first request against the Municipal DCC Data API.

Usage:
  python examples/python/get_rates.py
  BASE_URL=http://127.0.0.1:8080 python examples/python/get_rates.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8080").rstrip("/")


def get(path: str, params: dict | None = None) -> dict:
    url = f"{BASE_URL}{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    try:
        munis = get("/municipalities")
    except urllib.error.URLError as exc:
        print(f"Could not reach API at {BASE_URL}: {exc}", file=sys.stderr)
        print("Start it with: ./scripts/run_api.sh", file=sys.stderr)
        return 1

    print("Municipalities:")
    for m in munis["municipalities"]:
        flag = " PROVISIONAL" if m["provisional"] else ""
        print(f"  - {m['slug']}: bylaw {m['bylaw_id']}, {m['rate_count']} rates{flag}")

    data = get(
        "/rates/victoria",
        {"use_type": "medium density", "charge_type": "Total DCC"},
    )
    print(f"\nVictoria filter result: provisional={data['provisional']} "
          f"method={data['source_retrieval_method']} count={data['count']}")
    for rate in data["rates"]:
        prov = rate["provenance"]
        print(f"  use_type={rate['use_type']!r}")
        print(f"  rate={rate['rate']} {rate['currency']} / {rate['unit']}")
        print(f"  provisional={prov['provisional']}")
        print(f"  source_url={prov['source_url']}")
        print(f"  bylaw_id={prov['bylaw_id']}  effective_date={rate['effective_date']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
