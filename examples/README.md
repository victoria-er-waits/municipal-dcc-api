# Examples

Default base URL: `http://127.0.0.1:8080` (override with `BASE_URL`).

| Path | What |
|---|---|
| [`curl/quickstart.sh`](curl/quickstart.sh) | Curl one-liners for health → municipalities → rates → changes |
| [`python/get_rates.py`](python/get_rates.py) | stdlib `urllib` script (no extra deps) |
| [`javascript/get_rates.mjs`](javascript/get_rates.mjs) | Node 18+ `fetch` |
| [`sample-responses/`](sample-responses/) | Saved JSON captured from the local API |

```bash
# from repo root, with API running
./examples/curl/quickstart.sh
python3 examples/python/get_rates.py
node examples/javascript/get_rates.mjs
```
