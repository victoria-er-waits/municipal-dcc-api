# Publish this repo to GitHub (human steps)

Day 4 prepared a clean local git commit of the public surface. **No remote was added and no GitHub repository was created** — that needs an explicit human confirmation.

Checked on 2026-10-05 (PT):

- `gh` is logged in as **kylethomas891615-hue** (scopes: `gist`, `read:org`, `repo`)
- Local repo: initialized, Day 4 commit present
- No `origin` remote yet

## Option A — GitHub CLI (recommended once you confirm the name)

Pick a public repo name, then run **exactly** (do not run until you intend to create it):

```bash
cd /workspace/municipal-dcc-api
gh repo create municipal-dcc-api --public --source=. --remote=origin --description "Canadian municipal development-cost-charge (DCC) rates as JSON — Surrey + Victoria MVP"
git push -u origin HEAD
```

Or create empty first, then push:

```bash
gh repo create municipal-dcc-api --public --description "Canadian municipal development-cost-charge (DCC) rates as JSON — Surrey + Victoria MVP"
git remote add origin https://github.com/kylethomas891615-hue/municipal-dcc-api.git
git push -u origin HEAD
```

Adjust the repo name / owner if you prefer a different slug or org.

## Option B — GitHub web UI

1. Create an **empty** public repository (no README / license / .gitignore — this tree already has them).
2. Then:

```bash
cd /workspace/municipal-dcc-api
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin HEAD
```

## Option C — Cursor / Origin remote

If you use Origin instead of GitHub.com, add that remote the same way (`git remote add origin <url>` then `git push -u origin HEAD`). Do not force-push.

## Notes

- Repo size is dominated by `sources/surrey_BYL_reg_21174.pdf` (~12 MB) plus schedule PNGs. Fine for GitHub; optional later cleanup is Git LFS or “download on build” instructions.
- `db/dcc.sqlite3` (~2.6 MB) is committed so clone → `./scripts/run_api.sh` works without a rebuild.
- Do **not** commit `.venv/`, `logs/`, or secrets (already gitignored).
