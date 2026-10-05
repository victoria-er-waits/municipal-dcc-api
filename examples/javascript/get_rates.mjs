#!/usr/bin/env node
/**
 * Minimal first request against the Municipal DCC Data API (Node 18+).
 *
 *   node examples/javascript/get_rates.mjs
 *   DCC_API_KEY=dcc_... node examples/javascript/get_rates.mjs
 *   BASE_URL=http://127.0.0.1:8080 node examples/javascript/get_rates.mjs
 *
 * If DCC_API_KEY is unset, a free key is created (POST /v1/keys) and printed — save it.
 */
const BASE_URL = (process.env.BASE_URL || "https://municipal-dcc-api.onrender.com").replace(/\/$/, "");
let API_KEY = process.env.DCC_API_KEY;

async function get(path, params) {
  const url = new URL(path, BASE_URL + "/");
  if (params) {
    for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
  }
  const res = await fetch(url, { headers: API_KEY ? { "X-API-Key": API_KEY } : {} });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${url}`);
  return res.json();
}

const munis = await get("/municipalities");
console.log("Municipalities:");
for (const m of munis.municipalities) {
  const flag = m.provisional ? " PROVISIONAL" : "";
  console.log(`  - ${m.slug}: bylaw ${m.bylaw_id}, ${m.rate_count} rates${flag} (min_plan=${m.min_plan})`);
}

if (!API_KEY) {
  const res = await fetch(`${BASE_URL}/v1/keys`, { method: "POST" });
  const body = await res.json();
  if (!res.ok) throw new Error(`Could not create a free key: ${res.status} ${JSON.stringify(body)}`);
  API_KEY = body.api_key;
  console.log(`\nCreated free API key (save it): export DCC_API_KEY=${API_KEY}`);
}

const data = await get("/rates/victoria", {
  use_type: "medium density",
  charge_type: "Total DCC",
});
console.log(
  `\nVictoria filter result: provisional=${data.provisional} ` +
    `method=${data.source_retrieval_method} count=${data.count}`,
);
for (const rate of data.rates) {
  const prov = rate.provenance;
  console.log(`  use_type=${JSON.stringify(rate.use_type)}`);
  console.log(`  rate=${rate.rate} ${rate.currency} / ${rate.unit}`);
  console.log(`  provisional=${prov.provisional}`);
  console.log(`  source_url=${prov.source_url}`);
  console.log(`  bylaw_id=${prov.bylaw_id}  effective_date=${rate.effective_date}`);
}
