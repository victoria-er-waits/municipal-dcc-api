#!/usr/bin/env node
/**
 * Minimal first request against the Municipal DCC Data API (Node 18+).
 *
 *   node examples/javascript/get_rates.mjs
 *   BASE_URL=http://127.0.0.1:8080 node examples/javascript/get_rates.mjs
 */
const BASE_URL = (process.env.BASE_URL || "http://127.0.0.1:8080").replace(/\/$/, "");

async function get(path, params) {
  const url = new URL(path, BASE_URL + "/");
  if (params) {
    for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
  }
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${url}`);
  return res.json();
}

const munis = await get("/municipalities");
console.log("Municipalities:");
for (const m of munis.municipalities) {
  const flag = m.provisional ? " PROVISIONAL" : "";
  console.log(`  - ${m.slug}: bylaw ${m.bylaw_id}, ${m.rate_count} rates${flag}`);
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
