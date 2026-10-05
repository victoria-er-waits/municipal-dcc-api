# Examples

Default base URL: `https://municipal-dcc-api.onrender.com` (interactive docs at `/docs`).
Override with `BASE_URL=http://127.0.0.1:8080` for a local Victoria-only server.
API key: set `DCC_API_KEY=dcc_…`; if unset, each script creates a **free** key (Victoria current rates, 50 req/day) and prints it.

| Path | What |
|---|---|
| [`curl/quickstart.sh`](curl/quickstart.sh) | Curl one-liners: health → municipalities → key → rates → changes |
| [`curl/stranger_journey.sh`](curl/stranger_journey.sh) | Full Day 5 flow: free key → Victoria OK → Surrey/changes/history 402 → daily-limit 429 → upgrade (admin unlock or Stripe Checkout) → paid access |
| [`python/get_rates.py`](python/get_rates.py) | stdlib `urllib` script (no extra deps) |
| [`javascript/get_rates.mjs`](javascript/get_rates.mjs) | Node 18+ `fetch` |
| [`sample-responses/`](sample-responses/) | Saved JSON for the free path and the Surrey 402. No Surrey rate body. |

```bash
# hosted API (default)
./examples/curl/quickstart.sh
python3 examples/python/get_rates.py
node examples/javascript/get_rates.mjs

# full paid-boundary journey; step 6 uses ADMIN_UNLOCK_TOKEN if set, otherwise Stripe Checkout
ADMIN_UNLOCK_TOKEN=... ./examples/curl/stranger_journey.sh
```
