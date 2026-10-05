#!/usr/bin/env python3
"""Minimal first request against the Municipal DCC Data API.

Usage:
  python examples/python/get_rates.py
  DCC_API_KEY=dcc_... python examples/python/get_rates.py
  BASE_URL=http://127.0.0.1:8080 python examples/python/get_rates.py

If DCC_API_KEY is unset, a free key is created (POST /v1/keys) and printed — save it.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = os.environ.get("BASE_URL", "https://municipal-dcc-api.onrender.com").rstrip("/")
API_KEY = os.environ.get("DCC_API_KEY")


def get(path: str, params: dict | None = None) -> dict:
    url = f"{BASE_URL}{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"X-API-Key": API_KEY} if API_KEY else {})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def create_free_key() -> str:
    req = urllib.request.Request(f"{BASE_URL}/v1/keys", data=b"", method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            key = json.loads(resp.read().decode("utf-8"))["api_key"]
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Could not create a free key: {exc.code} {exc.read().decode('utf-8')}")
    print(f"Created free API key (save it): export DCC_API_KEY={key}\n")
    return key


def main() -> int:
    try:
        munis = get("/municipalities")
    except urllib.error.URLError as exc:
        print(f"Could not reach API at {BASE_URL}: {exc}", file=sys.stderr)
        print("Hosted docs: https://municipal-dcc-api.onrender.com/docs", file=sys.stderr)
        print("Or start a local Victoria-only server: ./scripts/run_api.sh", file=sys.stderr)
        return 1

    print("Municipalities:")
    for m in munis["municipalities"]:
        flag = " PROVISIONAL" if m["provisional"] else ""
        print(f"  - {m['slug']}: bylaw {m['bylaw_id']}, {m['rate_count']} rates{flag} (min_plan={m['min_plan']})")

    global API_KEY
    if not API_KEY:
        API_KEY = create_free_key()

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
