# Static results site

An interactive, read-only snapshot of all saved backtests — clusters runs by
strategy, compares parameter variations, overlays equity curves, and shows full
metrics + in/out-of-sample splits + trades. Pure static files (HTML/CSS/JS); the
data lives in `data.json`, generated from your local results.

## Publish (Vercel)

1. Run backtests locally, then export the snapshot:
   ```bash
   python export_site.py        # writes site/data.json
   ```
2. Deploy the `site/` folder:
   ```bash
   npm i -g vercel              # once
   cd site && vercel --prod     # first run links/creates the project
   ```
   Vercel detects a static site (no build step) and gives you a public URL.

   **Or via Git integration:** in the Vercel dashboard, import the repo and set
   **Root Directory = `site`**, framework preset **Other**. Re-export + commit
   `site/data.json` (it's gitignored by default) whenever you want to refresh.

## Preview locally

`fetch()` needs HTTP (not `file://`), so serve the folder:
```bash
cd site && python -m http.server 8000   # open http://localhost:8000
```

## Notes
- Only results are exported — no API keys, no raw market data. `.env`,
  `.kite_cache/`, and `results/` never leave your machine.
- Equity curves are downsampled (daily) so the snapshot stays small.
